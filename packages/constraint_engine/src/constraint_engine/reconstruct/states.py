"""Machine states from events and calendar: where every shift minute went (pure).

Shift time = uncovered breaks + planned maintenance + unplanned stops + available time.
Available time = running + setup + blocked + starved + unknown. Blocked needs move/scan events:
the machine finished a job but the order has not yet arrived at the next station. Without them,
blocked time is reported as Missing and counted as starved.

Unknown time: a start without an end (or an end without a start) means the machine did
something we cannot see. From that event to the machine's next (or previous) event is
``unknown``, not starved, so a lost event lowers confidence instead of changing the answer.
"""

from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from cip_schema.master import CalendarKind
from cip_schema.transactional import EventType
from constraint_engine.figure import Confidence, Missing
from constraint_engine.intervals import Interval, intersect, normalise, subtract, total
from constraint_engine.io.plant_loader import LoadedPlant
from constraint_engine.reconstruct.durations import Operations, pair_operations
from constraint_engine.reconstruct.timeline import MachineTime, machine_time, to_min

STATES = ("break", "maintenance", "down", "running", "setup", "blocked", "starved")
UNKNOWN = "unknown"
"""Shift time the events cannot explain (see module docstring); outside STATES on purpose."""


@dataclass
class MachineStates:
    resource_code: str
    shift: list[Interval]
    intervals: dict[str, list[Interval]] = field(default_factory=dict)
    blocked_missing: Missing | None = None

    def minutes(self, window: Interval | None = None) -> dict[str, float]:
        w = [window] if window else None
        out = {"shift": total(intersect(self.shift, w) if w else self.shift)}
        for state in (*STATES, UNKNOWN):
            iv = self.intervals.get(state, [])
            out[state] = total(intersect(iv, w) if w else iv)
        return out


def data_end(plant: LoadedPlant) -> float:
    """End of the shift in which the last event happened (end of the data)."""
    last = max((to_min(e.at) for e in plant.events), default=0.0)
    ends = [
        to_min(w.end_at)
        for w in plant.calendar
        if w.kind is CalendarKind.SHIFT and to_min(w.start_at) <= last
    ]
    return max([last, *ends]) if ends else last


def _blocked(plant: LoadedPlant, ops: Operations) -> dict[str, list[Interval]]:
    station_of = {r.resource_code: r.station_code for r in plant.resources}
    arrivals: dict[str, list[tuple[float, str | None]]] = defaultdict(list)
    for e in plant.events:
        if e.event_type in (EventType.SCAN, EventType.MOVE) and e.order_id:
            arrivals[e.order_id].append(
                (to_min(e.at), e.station_code or station_of.get(e.resource_code or ""))
            )
    for v in arrivals.values():
        v.sort(key=lambda a: a[0])
    blocked: dict[str, list[Interval]] = defaultdict(list)
    for row in ops.jobs.iter_rows(named=True):
        end = to_min(row["end_at"])
        nxt = next((t for t, _ in arrivals.get(row["order_id"], []) if t >= end), None)
        if nxt is not None and nxt > end:
            blocked[row["resource_code"]].append((end, nxt))
    return blocked


def _unknown(plant: LoadedPlant, ops: Operations) -> dict[str, list[Interval]]:
    """From a start without an end to the machine's next event; from the previous event to an
    end without a start. Starts still running at the end of the data are not unknown."""
    at: dict[str, list[float]] = defaultdict(list)
    for e in plant.events:
        if e.resource_code and e.event_type not in (EventType.SCAN, EventType.MOVE):
            at[e.resource_code].append(to_min(e.at))
    for v in at.values():
        v.sort()
    out: dict[str, list[Interval]] = defaultdict(list)
    for u in ops.unpaired:
        code = u.event.resource_code
        if code is None or u.missing.reason == "still running at the end of the data":
            continue
        times, t = at[code], to_min(u.event.at)
        if u.missing.what == "end":
            i = bisect_right(times, t)
            if i < len(times):
                out[code].append((t, times[i]))
        else:
            i = bisect_left(times, t) - 1
            if i >= 0:
                out[code].append((times[i], t))
    return out


def machine_states(plant: LoadedPlant, ops: Operations | None = None) -> dict[str, MachineStates]:
    ops = ops or pair_operations(plant)
    times = machine_time(plant)
    end = data_end(plant)
    has_moves = any(e.event_type in (EventType.SCAN, EventType.MOVE) for e in plant.events)
    blocked = _blocked(plant, ops) if has_moves else {}
    unknown = _unknown(plant, ops)
    jobs: dict[str, list[Interval]] = defaultdict(list)
    for row in ops.jobs.iter_rows(named=True):
        jobs[row["resource_code"]].append((to_min(row["start_at"]), to_min(row["end_at"])))
    for u in ops.unpaired:
        if u.missing.reason == "still running at the end of the data" and u.event.resource_code:
            jobs[u.event.resource_code].append((to_min(u.event.at), end))
    setups: dict[str, list[Interval]] = defaultdict(list)
    for row in ops.setups.iter_rows(named=True):
        setups[row["resource_code"]].append((to_min(row["start_at"]), to_min(row["end_at"])))
    return {
        code: _states(
            code,
            mt,
            end,
            jobs[code],
            setups[code],
            blocked.get(code, []),
            has_moves,
            unknown.get(code, []),
        )
        for code, mt in times.items()
    }


def _states(
    code: str,
    mt: MachineTime,
    end: float,
    jobs: list[Interval],
    setups: list[Interval],
    blocked_raw: list[Interval],
    has_moves: bool,
    unknown_raw: list[Interval] | None = None,
) -> MachineStates:
    window = [(min((s for s, _ in mt.shifts), default=0.0), end)]
    shift = intersect(mt.shifts, window)
    available = intersect(mt.available, window)
    running = intersect(normalise(jobs), available)
    setup = subtract(intersect(normalise(setups), available), running)
    busy = normalise(running + setup)
    unknown = subtract(intersect(normalise(unknown_raw or []), available), busy)
    seen = normalise(busy + unknown)
    blocked = subtract(intersect(normalise(blocked_raw), available), seen)
    starved = subtract(available, normalise(seen + blocked))
    states = MachineStates(code, shift)
    states.intervals = {
        "break": intersect(mt.breaks, shift),
        "maintenance": intersect(subtract(mt.maintenance, mt.breaks), shift),
        "down": intersect(mt.stops, shift),
        "running": running,
        "setup": setup,
        "blocked": blocked,
        "starved": starved,
        UNKNOWN: unknown,
    }
    if not has_moves:
        states.blocked_missing = Missing(
            "blocked time",
            "no move/scan events: blocked time cannot be told apart from starved",
            Confidence.MEDIUM,
        )
    return states


def period_windows(start: datetime, end: datetime, tz: str, freq: str) -> dict[str, Interval]:
    """Local-time days (``D``), weeks (``W``, ISO) or months (``M``) between start and end, as
    minute windows."""
    from datetime import timedelta
    from zoneinfo import ZoneInfo

    zone = ZoneInfo(tz)
    local = start.astimezone(zone).replace(hour=0, minute=0, second=0, microsecond=0)
    if freq == "W":
        local -= timedelta(days=local.weekday())
    elif freq == "M":
        local = local.replace(day=1)
    out: dict[str, Interval] = {}
    while local < end:
        if freq == "D":
            nxt = local + timedelta(days=1)
            label = local.date().isoformat()
        elif freq == "W":
            nxt = local + timedelta(days=7)
            iso = local.isocalendar()
            label = f"{iso.year}-W{iso.week:02d}"
        else:
            nxt = (local.replace(day=28) + timedelta(days=4)).replace(day=1)
            label = f"{local.year:04d}-{local.month:02d}"
        out[label] = (to_min(local.replace(tzinfo=zone)), to_min(nxt.replace(tzinfo=zone)))
        local = nxt
    return out
