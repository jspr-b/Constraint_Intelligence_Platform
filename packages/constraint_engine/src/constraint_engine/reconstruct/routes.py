"""The plant's flow as found in the event log (ADR-0009, CI0005 seq 06).

Each job's path is its steps in order of their start touchpoints; a restart at the same step is
one visit, and a step visited again later is rework. Paths of all jobs are counted as routes
(the main route and side routes, with the share of jobs on each) and as arrows between steps
(with the share of the jobs leaving a step that go each way).

Parts are less certain when the data behind them is: jobs whose finish at a step is missing,
jobs at two steps at the same time (parallel work or a forgotten scan), and rework. Every share
is a Figure with the jobs counted and the period.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from itertools import pairwise

from constraint_engine.figure import Figure
from constraint_engine.formulas.registry import Calc, Resolved, formula
from constraint_engine.io.plant_loader import LoadedPlant

TOP_ROUTES = 6
"""Routes shown one by one; the others are counted together."""
UNCERTAIN_SHARE_PCT = 5.0
"""A route or arrow is less certain when at least this share of its jobs has a missing finish
or overlapping steps."""


@formula(
    "flow_share_pct",
    1,
    "share of jobs = jobs that go this way ÷ jobs counted × 100; jobs counted are all jobs for a "
    "route and the jobs leaving the step for an arrow",
    unit="pct",
)
def flow_share(jobs: int, of: int, period: tuple[datetime | None, datetime | None]) -> Calc:
    def compute(i: Resolved) -> float:
        n, of = int(i["jobs_this_way"]), int(i["jobs_counted"])
        return round(100 * n / of, 1) if of else 0.0

    return Calc(
        inputs={"jobs_this_way": jobs, "jobs_counted": of},
        compute=compute,
        period_start_at=period[0],
        period_end_at=period[1],
    )


@dataclass(frozen=True)
class Route:
    steps: tuple[str, ...]
    jobs: int
    share: Figure
    """Of all jobs counted."""
    rework: bool
    uncertain_jobs: int
    """Jobs on this route with a missing finish or overlapping steps."""

    @property
    def less_certain(self) -> bool:
        return self.rework or 100 * self.uncertain_jobs >= UNCERTAIN_SHARE_PCT * self.jobs


@dataclass(frozen=True)
class Arrow:
    from_step: str
    to_step: str
    jobs: int
    share: Figure
    """Of the jobs leaving ``from_step`` for another step."""
    rework: bool
    """The jobs go back to a step they visited before."""
    uncertain_jobs: int

    @property
    def less_certain(self) -> bool:
        return self.rework or 100 * self.uncertain_jobs >= UNCERTAIN_SHARE_PCT * self.jobs


@dataclass(frozen=True)
class FlowStep:
    code: str
    jobs: int
    """Jobs that visited the step at least once."""
    first: int
    """Jobs whose path starts here (from Input)."""
    last: int
    """Jobs whose path ends here (to Output)."""
    missing_finish: int
    """Visits with a start but no finish."""


@dataclass(frozen=True)
class PlantFlow:
    jobs: int
    routes: list[Route]
    other_routes_jobs: int
    arrows: list[Arrow]
    steps: list[FlowStep]
    period_start_at: datetime | None
    period_end_at: datetime | None
    overlapping_jobs: int = 0
    rule: str = field(
        default="steps of a job in order of their start touchpoints; a restart at the same step "
        "is one visit; rework is a step visited again later"
    )


@dataclass
class _Visit:
    step: str
    start: datetime
    end: datetime | None


def _visits(plant: LoadedPlant) -> dict[str, list[_Visit]]:
    """Per job, its visits in start order, each with the finish at that step (if any)."""
    starts: dict[str, list[tuple[datetime, str]]] = defaultdict(list)
    ends: dict[tuple[str, str], list[datetime]] = defaultdict(list)
    for e in plant.events:
        if not e.order_id or not e.resource_code:
            continue
        if e.event_type == "start":
            starts[e.order_id].append((e.at, e.resource_code))
        elif e.event_type == "end":
            ends[(e.order_id, e.resource_code)].append(e.at)
    for times in ends.values():
        times.sort()
    out: dict[str, list[_Visit]] = {}
    for job, items in starts.items():
        visits: list[_Visit] = []
        for at, step in sorted(items):
            if visits and visits[-1].step == step:
                continue  # a restart at the same step is one visit
            visits.append(_Visit(step, at, None))
        for i, v in enumerate(visits):
            later = next((w.start for w in visits[i + 1 :] if w.step == v.step), None)
            v.end = next(
                (
                    t
                    for t in ends.get((job, v.step), [])
                    if t >= v.start and (later is None or t <= later)
                ),
                None,
            )
        out[job] = visits
    return out


def plant_flow(plant: LoadedPlant) -> PlantFlow:
    """Routes, arrows and steps of the plant's jobs, from their touchpoints."""
    visits = _visits(plant)
    times = [v.start for vs in visits.values() for v in vs]
    period = (min(times, default=None), max(times, default=None))
    routes: Counter[tuple[str, ...]] = Counter()
    route_uncertain: Counter[tuple[str, ...]] = Counter()
    arrows: Counter[tuple[str, str]] = Counter()
    arrow_rework: set[tuple[str, str]] = set()
    arrow_uncertain: Counter[tuple[str, str]] = Counter()
    visited: Counter[str] = Counter()
    first: Counter[str] = Counter()
    last: Counter[str] = Counter()
    missing: Counter[str] = Counter()
    overlapping = 0
    for vs in visits.values():
        path = tuple(v.step for v in vs)
        routes[path] += 1
        visited.update(set(path))
        first[path[0]] += 1
        last[path[-1]] += 1
        for v in vs:
            if v.end is None:
                missing[v.step] += 1
        overlap = any(a.end is not None and b.start < a.end for a, b in pairwise(vs))
        overlapping += overlap
        unsure = overlap or any(v.end is None for v in vs)
        route_uncertain[path] += unsure
        seen: set[str] = set()
        for a, b in pairwise(vs):
            seen.add(a.step)
            key = (a.step, b.step)
            arrows[key] += 1
            if b.step in seen:
                arrow_rework.add(key)
            if a.end is None or (a.end is not None and b.start < a.end):
                arrow_uncertain[key] += 1
    jobs = len(visits)
    leaving: Counter[str] = Counter()
    for (src, _), n in arrows.items():
        leaving[src] += n
    top = routes.most_common(TOP_ROUTES)
    return PlantFlow(
        jobs=jobs,
        routes=[
            Route(r, n, flow_share(n, jobs, period), len(set(r)) < len(r), route_uncertain[r])
            for r, n in top
        ],
        other_routes_jobs=jobs - sum(n for _, n in top),
        arrows=[
            Arrow(
                a,
                b,
                n,
                flow_share(n, leaving[a], period),
                (a, b) in arrow_rework,
                arrow_uncertain[(a, b)],
            )
            for (a, b), n in sorted(arrows.items())
        ],
        steps=[
            FlowStep(code, visited[code], first[code], last[code], missing[code])
            for code in sorted(visited)
        ],
        period_start_at=period[0],
        period_end_at=period[1],
        overlapping_jobs=overlapping,
    )
