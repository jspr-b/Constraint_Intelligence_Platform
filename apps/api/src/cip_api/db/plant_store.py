"""Store a plant in the database and read it back (ADR-0010).

A plant's data is rebuilt from its kept imports: the event log adds (an event counted once by its
id), every other list comes from the newest import that brings it. Rows entered or edited in the
app have no ``import_id`` and are never touched by a rebuild. Everything runs inside the caller's
tenant transaction, so row-level security applies to every read and write.
"""

import hashlib
import json
import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Connection, Table, delete, select, text
from sqlalchemy.dialects.postgresql import insert

from cip_api.db.models import Base
from cip_connectors.importer import Fixes
from constraint_engine.figure import Missing
from constraint_engine.io.plant_loader import LoadedPlant
from constraint_engine.io.records import load_records

# LoadedPlant attribute -> table. Routings are stored as their steps.
TABLES: dict[str, str] = {
    "stations": "stations",
    "resources": "resources",
    "products": "products",
    "routings": "routing_steps",
    "orders": "orders",
    "events": "operation_events",
    "calendar": "calendar_windows",
    "resource_operations": "resource_operations",
    "changeovers": "changeovers",
    "overtime": "overtime_worked",
    "capacity_costs": "capacity_costs",
    "outsourcing": "outsourcing_prices",
    "teams": "teams",
    "team_shifts": "team_shifts",
}


def _value(value: Any) -> Any:
    if isinstance(value, Missing):
        return None
    if isinstance(value, tuple | list):
        return ",".join(str(v) for v in value)
    return value


def _rows(plant: LoadedPlant, name: str) -> list[dict[str, Any]]:
    records: list[BaseModel] = getattr(plant, name)
    if name == "routings":
        return [
            {"sku": r.sku, **s.model_dump()}  # type: ignore[attr-defined]
            for r in records
            for s in r.steps  # type: ignore[attr-defined]
        ]
    return [r.model_dump() for r in records]


LISTS = tuple(name for name in TABLES if name != "events")
# Tables keyed by a running number: an imported row clashes with an app row on these columns.
NATURAL_KEYS: dict[str, tuple[str, ...]] = {
    "calendar_windows": ("resource_code", "kind", "start_at", "end_at"),
    "team_shifts": ("team_code", "start_at", "end_at"),
    "outsourcing_prices": ("operation", "sku"),
}


# Rows a client may remove on Setup or Calendar, by their key columns (ADR-0010 point 7).
REMOVE_KEYS: dict[str, tuple[str, ...]] = {
    "resources": ("resource_code",),
    "stations": ("station_code",),
    "calendar_windows": ("resource_code", "kind", "start_at", "end_at"),
}


def key_text(value: Any) -> str:
    """A key value as text, the same for a row read back and a row about to be written."""
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    return str(value)


def row_fixes(conn: Connection, import_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, Fixes]:
    """The fixes in use per import: file -> line -> {column: value}, or None for a line left
    out (a line left out wins over a value fixed on it)."""
    ids = list(import_ids)
    out: dict[uuid.UUID, dict[str, dict[int, dict[str, str] | None]]] = defaultdict(dict)
    if not ids:
        return {}
    rows = conn.execute(
        text(
            'SELECT import_id, file, line, action, "column", value FROM corrections '
            "WHERE import_id = ANY(:ids) AND action IN ('set', 'exclude') AND undone_at IS NULL "
            "ORDER BY created_at"
        ),
        {"ids": ids},
    )
    for r in rows:
        lines = out[r.import_id].setdefault(r.file, {})
        if r.action == "exclude":
            lines[r.line] = None
        elif (fix := lines.get(r.line, {})) is not None:
            lines[r.line] = {**fix, r.column: r.value}
    return dict(out)


def fixes_digest(fixes: Fixes | None) -> str:
    """Stamp of the fixes an import was mapped with; a different stamp means map it again."""
    body = json.dumps(
        {f: {str(n): v for n, v in sorted(lines.items())} for f, lines in (fixes or {}).items()},
        sort_keys=True,
    )
    return hashlib.sha256(body.encode()).hexdigest()


def removed_rows(conn: Connection, plant_code: str) -> dict[str, set[tuple[str, ...]]]:
    """Imported rows removed on Setup or Calendar, per table, by their key as text."""
    out: dict[str, set[tuple[str, ...]]] = defaultdict(set)
    for target, key in conn.execute(
        text(
            "SELECT target, target_key FROM corrections WHERE plant_code = :p "
            "AND action = 'remove' AND undone_at IS NULL"
        ),
        {"p": plant_code},
    ):
        out[target].add(tuple(json.loads(key)))
    return out


@dataclass
class EventCounts:
    """What one import did to the event log (ADR-0010)."""

    added: int = 0
    already_there: int = 0
    changed: int = 0
    repeated_in_file: int = 0
    period_start_at: datetime | None = None
    period_end_at: datetime | None = None


@dataclass
class Merged:
    """The plant from its kept imports: records per type, each with the import it came from."""

    records: dict[str, list[tuple[uuid.UUID, dict[str, Any]]]] = field(default_factory=dict)
    events: dict[uuid.UUID, EventCounts] = field(default_factory=dict)
    lists_from: dict[str, uuid.UUID] = field(default_factory=dict)


def merge_imports(imports: Sequence[tuple[uuid.UUID, LoadedPlant]]) -> Merged:
    """Kept imports in upload order -> the plant's records. Pure.

    Events: the first time an id is seen it is added; seen again with the same values it is
    already there; with other values (only possible with the plant's own event ids) the newer
    import's values win and it counts as changed. Lists: the newest import that brings a list
    replaces it; a list no import brings is absent.
    """
    merged = Merged()
    events: dict[str, tuple[uuid.UUID, dict[str, Any]]] = {}
    for import_id, plant in imports:
        counts = EventCounts()
        seen: set[str] = set()
        for record in _rows(plant, "events"):
            key = str(record["event_id"])
            at = record["at"]
            counts.period_start_at = min(filter(None, (counts.period_start_at, at)))
            counts.period_end_at = max(filter(None, (counts.period_end_at, at)))
            if key in seen:
                counts.repeated_in_file += 1
                continue
            seen.add(key)
            before = events.get(key)
            if before is None:
                counts.added += 1
            elif before[1] == record:
                counts.already_there += 1
                continue
            else:
                counts.changed += 1
            events[key] = (import_id, record)
        merged.events[import_id] = counts
        for name in LISTS:
            if getattr(plant, name):
                merged.lists_from[name] = import_id
                merged.records[name] = [(import_id, r) for r in _rows(plant, name)]
    merged.records["events"] = list(events.values())
    return merged


def rebuild_plant_data(
    conn: Connection, tenant: uuid.UUID, plant_code: str, merged: Merged
) -> dict[str, int]:
    """Replace the plant's imported rows with ``merged``; app rows stay. Returns counts.

    An imported row that clashes with an app row (same key) is skipped: what was entered or
    edited in the app wins. An imported row removed on Setup or Calendar stays out.
    """
    conn.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"plant:{tenant}:{plant_code}"}
    )
    counts: dict[str, int] = {}
    removed = removed_rows(conn, plant_code)
    for name, table_name in TABLES.items():
        table: Table = Base.metadata.tables[table_name]
        conn.execute(
            delete(table).where(table.c.plant_code == plant_code, table.c.import_id.is_not(None))
        )
        columns = [
            c.name
            for c in table.columns
            if not (c.primary_key and c.autoincrement is True) and c.name != "import_id"
        ]
        rows = [
            {
                "import_id": import_id,
                **{
                    c: (
                        tenant
                        if c == "tenant_id"
                        else plant_code
                        if c == "plant_code"
                        else _value(record.get(c))
                    )
                    for c in columns
                },
            }
            for import_id, record in merged.records.get(name, [])
        ]
        if keys := NATURAL_KEYS.get(table_name):
            app = {
                tuple(r)
                for r in conn.execute(
                    select(*(table.c[k] for k in keys)).where(
                        table.c.plant_code == plant_code, table.c.import_id.is_(None)
                    )
                )
            }
            rows = [r for r in rows if tuple(r[k] for k in keys) not in app]
        if gone := removed.get(table_name):
            keys = REMOVE_KEYS[table_name]
            rows = [r for r in rows if tuple(key_text(r[k]) for k in keys) not in gone]
        for start in range(0, len(rows), 5000):
            conn.execute(insert(table).on_conflict_do_nothing(), rows[start : start + 5000])
        counts[name] = len(rows)
    return counts


def load_plant_from_db(conn: Connection, tenant: uuid.UUID, plant_code: str) -> LoadedPlant:
    """The plant as the engine reads it: from the database rows, not from files (ADR-0010)."""
    plant = conn.execute(
        text("SELECT plant_code, name, timezone_iana FROM plants WHERE plant_code = :p"),
        {"p": plant_code},
    ).one()
    records: dict[str, list[dict[str, Any]]] = {}
    for name, table_name in TABLES.items():
        table: Table = Base.metadata.tables[table_name]
        skip = {"tenant_id", "plant_code", "import_id"}
        cols = [
            c
            for c in table.columns
            if c.name not in skip and not (c.primary_key and c.autoincrement is True)
        ]
        order = [table.c.at, table.c.event_id] if name == "events" else list(table.primary_key)
        query = select(*cols).where(table.c.plant_code == plant_code).order_by(*order)
        records[name] = [dict(r._mapping) for r in conn.execute(query)]
    return load_records(dict(plant._mapping), records, tenant_id=tenant)
