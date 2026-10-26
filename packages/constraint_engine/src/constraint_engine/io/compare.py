"""What an upload changes in a plant: the plant now against the plant after it (ADR-0010).

Pure: both plants come in as ``LoadedPlant``; counts are of records, compared by their keys.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from constraint_engine.io.plant_loader import LoadedPlant

# Record type -> its key; types without a natural key are compared as counts only.
KEYS: dict[str, Callable[[Any], str]] = {
    "stations": lambda r: r.station_code,
    "resources": lambda r: r.resource_code,
    "products": lambda r: r.sku,
    "routings": lambda r: r.sku,
    "orders": lambda r: r.order_id,
    "teams": lambda r: r.team_code,
}
COUNTED = (
    "calendar",
    "resource_operations",
    "changeovers",
    "overtime",
    "capacity_costs",
    "outsourcing",
    "team_shifts",
)


@dataclass(frozen=True)
class ListChange:
    """One record type: rows before and after; new and gone keys where the type has keys."""

    name: str
    before: int
    after: int
    new: tuple[str, ...] = ()
    gone: tuple[str, ...] = ()


@dataclass(frozen=True)
class Warning:
    """Something the client should look at before running: a code and the affected items."""

    code: str
    """``steps_removed_with_events``, ``events_removed`` or ``period_shrinks``."""
    items: tuple[str, ...] = ()
    count: int = 0


@dataclass
class Preview:
    events_before: int = 0
    events_after: int = 0
    events_added: int = 0
    events_removed: int = 0
    period_before: tuple[datetime | None, datetime | None] = (None, None)
    period_after: tuple[datetime | None, datetime | None] = (None, None)
    lists: list[ListChange] = field(default_factory=list)
    warnings: list[Warning] = field(default_factory=list)


def _period(plant: LoadedPlant) -> tuple[datetime | None, datetime | None]:
    times = [e.at for e in plant.events]
    return (min(times), max(times)) if times else (None, None)


def compare_plants(before: LoadedPlant, after: LoadedPlant) -> Preview:
    """Events by id (added, removed), lists by key (new, gone) or count, and warnings."""
    ids_before = {e.event_id for e in before.events}
    ids_after = {e.event_id for e in after.events}
    preview = Preview(
        events_before=len(ids_before),
        events_after=len(ids_after),
        events_added=len(ids_after - ids_before),
        events_removed=len(ids_before - ids_after),
        period_before=_period(before),
        period_after=_period(after),
    )
    for name, key in KEYS.items():
        old = {key(r) for r in getattr(before, name)}
        new = {key(r) for r in getattr(after, name)}
        if old != new or len(getattr(before, name)) != len(getattr(after, name)):
            preview.lists.append(
                ListChange(
                    name, len(old), len(new), tuple(sorted(new - old)), tuple(sorted(old - new))
                )
            )
    for name in COUNTED:
        b, a = getattr(before, name), getattr(after, name)
        if b != a:
            preview.lists.append(ListChange(name, len(b), len(a)))

    gone_steps = {key for c in preview.lists if c.name == "resources" for key in c.gone}
    with_events = sorted({e.resource_code for e in before.events if e.resource_code in gone_steps})
    if with_events:
        preview.warnings.append(
            Warning("steps_removed_with_events", tuple(with_events), len(with_events))
        )
    if preview.events_removed:
        preview.warnings.append(Warning("events_removed", count=preview.events_removed))
    (b_start, b_end), (a_start, a_end) = preview.period_before, preview.period_after
    if (
        b_start
        and b_end
        and (a_start is None or a_end is None or a_start > b_start or a_end < b_end)
    ):
        preview.warnings.append(Warning("period_shrinks"))
    return preview
