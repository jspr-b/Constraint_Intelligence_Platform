"""The confirmed summary as an import mapping (ADR-0011): what the client confirmed is what runs.

A ``Plan`` is the summary in plain terms: which table fills which standard table, which column
fills which field, what each code means (or that its rows are left out), how each date column
is written, the unit of each duration, and the names and kinds the client gave the steps.
``build_mapping`` turns it into the same ``MappingSet`` a hand-written mapping file gives, so
the import, its checks and its rejected rows work the same. Steps and stations keep the plant's
own codes. Nothing is filled in that the plan does not say.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from cip_connectors.convert import as_code
from cip_connectors.importer import REQUIRED, STANDARD_COLUMNS
from cip_connectors.mapping import FieldRule, MappingSet, TableMapping, ValueType
from cip_connectors.wizard.codes import CODE_FIELDS, YES_NO_FIELDS

if TYPE_CHECKING:
    from cip_connectors.wizard import Recognised

SOURCE_SYSTEM = "WIZARD"
"""The mapping's name when it comes from a confirmed summary."""

INT_FIELDS = {"quantity_units", "scrap_units", "operation_seq", "iso_year", "iso_week"}
LIST_FIELDS = {"routings.alternative_resource_codes", "teams.resource_codes"}


def value_type(target: str) -> ValueType:
    """How a standard field's values are converted, from its name (units are in every name)."""
    name = target.split(".", 1)[1]
    if target in YES_NO_FIELDS:
        return "bool"
    if target in LIST_FIELDS:
        return "list"
    if "eur_cents" in name:
        return "eur_cents"
    if name == "at" or name.endswith("_at"):
        return "datetime"
    if name in INT_FIELDS or name == "positions" or name == "parallel_units":
        return "int"
    if name.endswith(("_min", "_h", "_min_per_unit")):
        return "decimal"
    return "str"


@dataclass
class PlanColumn:
    table: str
    column: str
    fields: list[str]
    part: Literal["date", "time"] | None = None
    """The column is the date or the time half of its field, with another column."""


@dataclass
class Plan:
    """A confirmed summary. Skipped tables and columns, and personal columns, are not in it."""

    tables: dict[str, str]
    """Table id -> its role (``events``, ``steps``, ``calendar``, ...)."""
    columns: list[PlanColumn]
    meanings: dict[str, dict[str, str]] = field(default_factory=dict)
    """Status field -> code -> meaning, or ``skip`` (its rows are left out)."""
    time_formats: dict[tuple[str, str], str] = field(default_factory=dict)
    """(table, column) -> date-time format of its values."""
    units: dict[tuple[str, str], Literal["min", "h"]] = field(default_factory=dict)
    """(table, column) -> the unit of a duration column."""
    decimal: str = "."
    timezone: str = "Europe/Amsterdam"
    yes_words: list[str] = field(default_factory=list)
    no_words: list[str] = field(default_factory=list)
    steps: dict[str, dict[str, str]] = field(default_factory=dict)
    """Step code -> what the client gave it: ``name`` and ``kind``."""


def _rule(plan: Plan, target: str, column: PlanColumn, time: PlanColumn | None) -> FieldRule:
    kind = value_type(target)
    table, name = target.split(".", 1)
    rule: dict[str, object] = {
        "from": column.column,
        "type": kind,
        "optional": name not in REQUIRED.get(table, ()),
    }
    if kind == "datetime":
        fmt = plan.time_formats.get((column.table, column.column))
        if fmt:  # real dates in a workbook are read as they are, whatever the format says
            rule["format"] = fmt
        if time is not None:
            rule["time_from"] = time.column
            rule["time_format"] = plan.time_formats.get((time.table, time.column)) or "%H:%M"
    if name.endswith(("resource_code", "station_code", "resource_codes")):
        rule["as_code"] = True
    if target in CODE_FIELDS:
        meanings = plan.meanings.get(target, {})
        rule["values"] = {c: m for c, m in meanings.items() if m != "skip"}
        rule["skip_values"] = tuple(sorted(c for c, m in meanings.items() if m == "skip"))
    field_unit = "h" if name.endswith("_h") else "min" if "_min" in name else None
    unit = plan.units.get((column.table, column.column))
    if field_unit and unit and unit != field_unit:
        rule["scale"] = "60" if unit == "h" else str(1 / 60)
    return FieldRule.model_validate(rule)


def _fields(plan: Plan, table: str) -> dict[str, dict[str, FieldRule]]:
    """Field rules per standard table for one export table."""
    halves: dict[str, dict[str, PlanColumn]] = defaultdict(dict)
    out: dict[str, dict[str, FieldRule]] = defaultdict(dict)
    for c in (c for c in plan.columns if c.table == table):
        for target in c.fields:
            if c.part is not None:
                halves[target][c.part] = c
            else:
                out[target.split(".", 1)[0]][target.split(".", 1)[1]] = _rule(plan, target, c, None)
    for target, parts in halves.items():
        if "date" in parts:
            rule = _rule(plan, target, parts["date"], parts.get("time"))
            out[target.split(".", 1)[0]][target.split(".", 1)[1]] = rule
    return out


def _complete(target: str, fields: dict[str, FieldRule]) -> dict[str, FieldRule]:
    """Fields the standard layout needs that an export never has: generated, or the step's own
    code where the export has no station (each step is then its own station)."""
    if target == "events":
        fields.setdefault("event_id", FieldRule.model_validate({"generate": "content_id"}))
    if target == "resources":
        code = fields.get("resource_code")
        if code is not None and "station_code" not in fields:
            fields["station_code"] = code
        if code is not None and "name" not in fields:
            fields["name"] = code
        fields.setdefault("kind", FieldRule.model_validate({"constant": "machine"}))
        fields.setdefault("parallel_units", FieldRule.model_validate({"constant": "1"}))
    return fields


def build_mapping(plan: Plan) -> MappingSet:
    """The import mapping for a confirmed summary."""
    tables: list[TableMapping] = []
    for table, role in plan.tables.items():
        by_target = _fields(plan, table)
        if role == "hour_bookings":  # one booking per row: its own fields and the job's
            by_target = {
                "bookings": {**by_target.get("events", {}), **by_target.get("bookings", {})}
            }
        if "resources" in by_target:
            resources = _complete("resources", by_target["resources"])
            station = resources["station_code"]
            stations = by_target.setdefault("stations", {})
            stations.setdefault("station_code", station)  # stations keep the plant's own name
            plain = stations["station_code"].model_copy(update={"as_code": False})
            stations.setdefault("name", plain)  # the name as the plant writes it
        for target, fields in by_target.items():
            if target not in STANDARD_COLUMNS and target != "bookings":
                continue
            tables.append(
                TableMapping(
                    source=table,
                    target=target,
                    unique=target == "stations",
                    fields=_complete(target, dict(fields)),
                )
            )
    overrides = {
        "resources": {
            as_code(code): {k: v for k, v in given.items() if k in ("name", "kind") and v}
            for code, given in plan.steps.items()
        }
    }
    return MappingSet(
        source_system=SOURCE_SYSTEM,
        timezone=plan.timezone,
        decimal=plan.decimal,
        true_values=tuple(w.lower() for w in plan.yes_words)
        or MappingSet.model_fields["true_values"].default,
        false_values=tuple(w.lower() for w in plan.no_words)
        or MappingSet.model_fields["false_values"].default,
        tables=tuple(tables),
        reader="wizard",
        overrides={k: {c: v for c, v in o.items() if v} for k, o in overrides.items()},
    )


def plan_from(found: "Recognised") -> Plan:
    """The plan of a recognition as the rules left it: what a client confirms by saying yes to
    every suggestion. Unknown codes stay without a meaning, so their rows are rejected."""
    tables: dict[str, str] = {r.table: r.role for r in found.roles if r.role and r.sure != "unsure"}
    columns = []
    for m in found.columns:
        if m.personal or m.target is None or m.sure == "unsure" or m.table not in tables:
            continue
        if isinstance(m.target, dict):
            ((key, target),) = m.target.items()
            part: Literal["date", "time"] = "date" if key.startswith("date") else "time"
            columns.append(PlanColumn(m.table, m.column, [target], part))
        else:
            targets = [m.target] if isinstance(m.target, str) else list(m.target)
            columns.append(PlanColumn(m.table, m.column, targets))
    meanings: dict[str, dict[str, str]] = {}
    for c in found.codes:
        if c.meaning is not None:
            meanings.setdefault(c.target, {})[c.code] = c.meaning
    f = found.formats
    return Plan(
        tables=tables,
        columns=columns,
        meanings=meanings,
        time_formats={(t.table, t.column): t.format for t in f.times if t.format},
        units={(u.table, u.column): "h" if u.unit == "h" else "min" for u in f.units},
        decimal=f.decimal,
        yes_words=f.yes_words,
        no_words=f.no_words,
    )
