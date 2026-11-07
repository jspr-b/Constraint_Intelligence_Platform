"""Where the event times come from (ADR-0011 §5, CI0005 seq 05).

Scans and terminals give exact times. Hour bookings give a start and a duration as booked, and
a booking with a date only is placed in its shift by the import (estimated). Bookings tell how
long a job was worked at a step; they do not record waiting, blocking, setups or stops. Answers
built on them are less sure, and the numbers that need those times are not available.
"""

from bisect import bisect_left
from collections import defaultdict
from dataclasses import dataclass, field

from constraint_engine.figure import Confidence
from constraint_engine.intervals import Interval
from constraint_engine.io.plant_loader import LoadedPlant
from constraint_engine.reconstruct.timeline import to_min

BOOKED_STEP_PCT = 50.0
"""A step whose start and end times come from bookings for at least this share: its setup,
stop, starved and blocked time is not available."""


@dataclass
class _Stamps:
    all: list[float] = field(default_factory=list)
    booked: list[float] = field(default_factory=list)
    """Booking or estimated."""
    estimated: list[float] = field(default_factory=list)


def _count(stamps: list[float], window: Interval) -> int:
    return bisect_left(stamps, window[1]) - bisect_left(stamps, window[0])


@dataclass(frozen=True)
class TimeSources:
    """Start and end times per step, by where they come from."""

    by_step: dict[str, _Stamps]
    overall: _Stamps

    def shares(self, window: Interval, step: str | None = None) -> tuple[float, float]:
        """Percent of start and end times in the window from bookings (estimated included),
        and percent estimated; for one step or the whole plant."""
        stamps = self.overall if step is None else self.by_step.get(step, _Stamps())
        total = _count(stamps.all, window)
        if not total:
            return 0.0, 0.0
        return (
            round(100 * _count(stamps.booked, window) / total, 1),
            round(100 * _count(stamps.estimated, window) / total, 1),
        )

    def cap(self, window: Interval) -> tuple[Confidence, str, float] | None:
        """The most an answer for the window can be trusted, with the reason code and share:
        estimated times allow low at most, booked times medium; None for scans only."""
        booked, estimated = self.shares(window)
        if estimated > 0:
            return Confidence.LOW, "times_estimated", estimated
        if booked > 0:
            return Confidence.MEDIUM, "times_from_bookings", booked
        return None


def time_sources(plant: LoadedPlant) -> TimeSources | None:
    """None when every time is from a scan (nothing to say)."""
    events = [e for e in plant.events if e.event_type in ("start", "end") and e.resource_code]
    if all(e.time_source == "scan" for e in events):
        return None
    by_step: dict[str, _Stamps] = defaultdict(_Stamps)
    overall = _Stamps()
    for e in events:
        at = to_min(e.at)
        for stamps in (by_step[str(e.resource_code)], overall):
            stamps.all.append(at)
            if e.time_source != "scan":
                stamps.booked.append(at)
            if e.time_source == "estimated":
                stamps.estimated.append(at)
    for stamps in (*by_step.values(), overall):
        stamps.all.sort()
        stamps.booked.sort()
        stamps.estimated.sort()
    return TimeSources(dict(by_step), overall)
