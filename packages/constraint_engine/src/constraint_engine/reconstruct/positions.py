"""Steps with several positions and shared teams: time counted in position-minutes (ADR-0009).

A handmade step has a number of staffed positions per shift (benches or places, a count, never
who); a team has a size per shift and covers one or more steps. Their states are counted in
position-minutes, so a share works the same way as for a machine with one position:

- shift = positions × shift minutes; breaks, maintenance and stops likewise
- running = jobs being worked, at most the positions (overlapping jobs each count)
- setup, unknown and blocked fill the positions that are not running, in that order
- starved = staffed positions with nothing to do

A team's busy positions are the jobs being worked at all of its steps. The team is on break or
in maintenance when all its steps are; a stop at one step does not stop the team.

For one position this gives exactly the minutes of the single-machine timeline.
"""

from bisect import bisect_right
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from cip_schema.master import CalendarKind
from constraint_engine.intervals import Interval, intersect, normalise
from constraint_engine.io.plant_loader import LoadedPlant
from constraint_engine.reconstruct.timeline import to_min

Counted = list[tuple[Interval, int]]
"""Shift windows with the number of staffed positions in each."""


class WeightedTimeline:
    """Segments [a, b) with a weight (positions); fast weighted minutes in any window."""

    def __init__(self, segments: Iterable[tuple[float, float, float]]) -> None:
        self.segments = sorted(s for s in segments if s[1] > s[0] and s[2] > 0)
        self.starts = [a for a, _, _ in self.segments]
        self.prefix = [0.0]
        for a, b, w in self.segments:
            self.prefix.append(self.prefix[-1] + (b - a) * w)

    def _upto(self, t: float) -> float:
        i = bisect_right(self.starts, t)
        if i == 0:
            return 0.0
        a, b, w = self.segments[i - 1]
        return self.prefix[i - 1] + (min(b, t) - a) * w

    def minutes(self, window: Interval | None = None) -> float:
        if window is None:
            return self.prefix[-1]
        return max(0.0, self._upto(window[1]) - self._upto(window[0]))


def step_positions(plant: LoadedPlant) -> dict[str, Counted]:
    """Staffed positions per shift for every step: the shift's count, else ``parallel_units``."""
    units = {r.resource_code: r.parallel_units for r in plant.resources}
    out: dict[str, Counted] = {code: [] for code in units}
    for w in plant.calendar:
        if w.kind is CalendarKind.SHIFT and w.resource_code in out:
            n = w.positions if w.positions is not None else units[w.resource_code]
            out[w.resource_code].append(((to_min(w.start_at), to_min(w.end_at)), n))
    return {code: sorted(windows) for code, windows in out.items()}


def team_positions(plant: LoadedPlant) -> dict[str, Counted]:
    out: dict[str, Counted] = {t.team_code: [] for t in plant.teams}
    for s in plant.team_shifts:
        if s.team_code in out:
            out[s.team_code].append(((to_min(s.start_at), to_min(s.end_at)), s.positions))
    return {code: sorted(windows) for code, windows in out.items()}


def pooled_steps(plant: LoadedPlant, positions: dict[str, Counted]) -> set[str]:
    """Steps counted in positions: more than one position in some shift, or covered by a team."""
    in_team = {code for t in plant.teams for code in t.resource_codes}
    return {
        code
        for code, windows in positions.items()
        if code in in_team or any(n > 1 for _, n in windows)
    }


def weighted_total(intervals: Sequence[Interval], counted: Counted, window: Interval) -> float:
    """Position-minutes of ``intervals`` inside ``window``: minutes × staffed positions."""
    return sum(
        n * sum(b - a for a, b in intersect(intervals, intersect([shift], [window])))
        for shift, n in counted
    )


KINDS = ("shift", "break", "maintenance", "down", "running", "setup", "unknown", "blocked")


@dataclass
class Swept:
    weighted: dict[str, WeightedTimeline]
    """Position-minutes per state (shift, break, maintenance, down, running, setup, blocked,
    starved, unknown)."""
    saturated: list[Interval]
    """When every staffed position was busy (running or setup): the step's active time for the
    active period method."""


def sweep(
    counted: Counted,
    window: Interval,
    breaks: Sequence[Interval],
    maintenance: Sequence[Interval],
    stops: Sequence[Interval],
    running: Sequence[Interval],
    setups: Sequence[Interval],
    unknown: Sequence[Interval],
    blocked: Sequence[Interval],
    has_moves: bool,
) -> Swept:
    """Where every staffed position-minute went, in ``window`` (see module docstring).

    ``breaks``, ``maintenance`` and ``stops`` are flags (each normalised); ``running``,
    ``setups``, ``unknown`` and ``blocked`` may overlap and are counted.
    """
    delta: dict[float, list[int]] = defaultdict(lambda: [0] * len(KINDS))

    def add(kind: str, items: Iterable[Interval], weight: int = 1) -> None:
        k = KINDS.index(kind)
        for a, b in items:
            a, b = max(a, window[0]), min(b, window[1])
            if b > a:
                delta[a][k] += weight
                delta[b][k] -= weight

    for shift, n in counted:
        add("shift", [shift], n)
    add("break", normalise(breaks))
    add("maintenance", normalise(maintenance))
    add("down", normalise(stops))
    add("running", running)
    add("setup", setups)
    add("unknown", unknown)
    add("blocked", blocked if has_moves else [])

    out: dict[str, list[tuple[float, float, float]]] = defaultdict(list)
    saturated: list[Interval] = []
    current = [0] * len(KINDS)
    last: float | None = None
    for t in sorted(delta):
        n = current[0]
        if last is not None and t > last and n > 0:
            seg = (last, t)
            out["shift"].append((*seg, n))
            if current[1] > 0:
                out["break"].append((*seg, n))
            elif current[2] > 0:
                out["maintenance"].append((*seg, n))
            elif current[3] > 0:
                out["down"].append((*seg, n))
            else:
                run = min(current[4], n)
                setup = min(current[5], n - run)
                unk = min(current[6], n - run - setup)
                blk = min(current[7], n - run - setup - unk)
                for state, w in (
                    ("running", run),
                    ("setup", setup),
                    ("unknown", unk),
                    ("blocked", blk),
                    ("starved", n - run - setup - unk - blk),
                ):
                    if w:
                        out[state].append((*seg, w))
                if run + setup >= n:
                    saturated.append(seg)
        for k, d in enumerate(delta[t]):
            current[k] += d
        last = t
    states = (*KINDS, "starved")
    return Swept({s: WeightedTimeline(out[s]) for s in states}, normalise(saturated))
