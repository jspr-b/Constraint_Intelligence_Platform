"""Machine time from the data: shifts, breaks, maintenance and stops, as minute intervals.

Minutes are counted from the Unix epoch (UTC); intervals are [start, end) as in
constraint_engine.intervals.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from cip_schema.master import CalendarKind
from cip_schema.transactional import EventType
from constraint_engine.intervals import Interval, intersect, normalise, subtract
from constraint_engine.io.plant_loader import LoadedPlant

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def to_min(moment: datetime) -> float:
    return (moment - EPOCH).total_seconds() / 60


def from_min(minute: float) -> datetime:
    return EPOCH + timedelta(minutes=minute)


@dataclass
class MachineTime:
    shifts: list[Interval] = field(default_factory=list)
    breaks: list[Interval] = field(default_factory=list)
    """Uncovered breaks only: the machine stops."""
    maintenance: list[Interval] = field(default_factory=list)
    stops: list[Interval] = field(default_factory=list)
    """Unplanned stops from down events (planned maintenance excluded)."""

    @property
    def production(self) -> list[Interval]:
        """Planned production time: shifts minus uncovered breaks minus planned maintenance."""
        return subtract(subtract(self.shifts, self.breaks), self.maintenance)

    @property
    def available(self) -> list[Interval]:
        """Production time minus unplanned stops."""
        return subtract(self.production, self.stops)


def _paired_stops(plant: LoadedPlant) -> dict[str, list[Interval]]:
    open_at: dict[str, float] = {}
    stops: dict[str, list[Interval]] = defaultdict(list)
    for e in sorted(plant.events, key=lambda e: e.at):
        if e.resource_code is None or e.down_reason_code == "PM":
            continue
        if e.event_type is EventType.DOWN_START:
            open_at[e.resource_code] = to_min(e.at)
        elif e.event_type is EventType.DOWN_END and e.resource_code in open_at:
            stops[e.resource_code].append((open_at.pop(e.resource_code), to_min(e.at)))
    return stops


def machine_time(plant: LoadedPlant) -> dict[str, MachineTime]:
    out = {r.resource_code: MachineTime() for r in plant.resources}
    for w in plant.calendar:
        mt = out.get(w.resource_code)
        if mt is None:
            continue
        interval = (to_min(w.start_at), to_min(w.end_at))
        if w.kind is CalendarKind.SHIFT:
            mt.shifts.append(interval)
        elif w.kind is CalendarKind.BREAK and not w.covered:
            mt.breaks.append(interval)
        elif w.kind is CalendarKind.MAINTENANCE:
            mt.maintenance.append(interval)
    for code, stops in _paired_stops(plant).items():
        if code in out:
            out[code].stops = stops
    for mt in out.values():
        mt.shifts, mt.breaks = normalise(mt.shifts), intersect(mt.breaks, normalise(mt.shifts))
        mt.maintenance = normalise(mt.maintenance)
        mt.stops = intersect(mt.stops, mt.production)
    return out
