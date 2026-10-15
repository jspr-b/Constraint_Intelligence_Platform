"""Calendar windows per machine, in minutes since the plant's start (UTC-correct, DST-aware)."""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from constraint_engine.synthetic.config import PlantCfg
from constraint_engine.synthetic.intervals import Interval, normalise


@dataclass
class Clock:
    """Converts between plant-local wall time and simulation minutes (UTC-based)."""

    origin_utc: datetime
    tz: ZoneInfo

    @classmethod
    def for_plant(cls, cfg: PlantCfg) -> "Clock":
        tz = ZoneInfo(cfg.timezone)
        local = datetime.combine(cfg.start_date, time(0, 0), tzinfo=tz)
        return cls(origin_utc=local.astimezone(UTC), tz=tz)

    def minute(self, day: date, at: time) -> float:
        local = datetime.combine(day, at, tzinfo=self.tz)
        return (local.astimezone(UTC) - self.origin_utc).total_seconds() / 60

    def at(self, minute: float) -> datetime:
        return self.origin_utc + timedelta(minutes=minute)


@dataclass
class BreakWindow:
    start: float
    end: float
    covered: bool


@dataclass
class MachineCalendar:
    shifts: list[Interval] = field(default_factory=list)
    breaks: list[BreakWindow] = field(default_factory=list)
    maintenance: list[Interval] = field(default_factory=list)

    def uncovered_breaks(self) -> list[Interval]:
        return normalise((b.start, b.end) for b in self.breaks if not b.covered)


def build_calendars(cfg: PlantCfg, clock: Clock, weeks: int) -> dict[str, MachineCalendar]:
    """Shift, break and maintenance windows per machine for the first ``weeks`` weeks."""
    cals = {r.code: MachineCalendar() for r in cfg.resources}
    for offset in range(weeks * 7):
        day = cfg.start_date + timedelta(days=offset)
        working = False
        for shift in cfg.shifts:
            if day.weekday() not in shift.weekdays:
                continue
            working = True
            start = clock.minute(day, shift.start)
            end_day = day if shift.end > shift.start else day + timedelta(days=1)
            end = clock.minute(end_day, shift.end)
            for cal in cals.values():
                cal.shifts.append((start, end))
        if not working:
            continue
        for brk in cfg.breaks:
            start = clock.minute(day, brk.start)
            for code, cal in cals.items():
                cal.breaks.append(BreakWindow(start, start + brk.minutes, code in brk.covered))
        for m in cfg.maintenance:
            if day.weekday() == m.weekday:
                start = clock.minute(day, m.start)
                cals[m.resource].maintenance.append((start, start + m.minutes))
    for cal in cals.values():
        cal.shifts = normalise(cal.shifts)
    return cals
