"""The client's edits to the flow found in the data (CI0005 seq 06, ADR-0011 §6).

The client checks the flow the engine found and corrects it: names steps, stations and routes,
adds steps, touchpoints and stations the data does not show, merges two codes that are the same
step, marks a route as wrong, and may estimate the share of a route it added.

Two pure functions:

- ``apply_flow_edits`` gives the plant the engine calculates on: merged codes become one step,
  added steps exist (with no data: not measured, nothing invented), and 'in parallel' counts
  set a step's capacity.
- ``edited_flow`` gives the flow the client sees: the found flow with the edits laid over it.
  Shares stay measured; an added step on a measured route takes over that route's jobs as
  *assumed*, and the client's own estimate is kept apart as an *estimate*. Neither is ever
  counted as measured.
"""

from dataclasses import dataclass, field, replace

from cip_schema.master import Resource, ResourceKind
from constraint_engine.figure import Figure
from constraint_engine.io.plant_loader import LoadedPlant
from constraint_engine.reconstruct.routes import Arrow, PlantFlow, flow_share


@dataclass(frozen=True)
class AddedStep:
    code: str
    name: str
    kind: str
    station_code: str | None
    after: str | None
    """The step it comes after (or None); with ``before`` it splits that route."""
    before: str | None


@dataclass(frozen=True)
class AddedRoute:
    route_id: str
    from_step: str
    to_step: str
    estimate_pct: int | None = None
    """The client's estimate of its share (1-100), never counted as measured."""


@dataclass(frozen=True)
class Touchpoint:
    touchpoint_id: str
    from_step: str
    to_step: str
    name: str
    at: float
    """Where on the arrow, 0-1."""


@dataclass(frozen=True)
class FlowEdits:
    steps_added: tuple[AddedStep, ...] = ()
    routes_added: tuple[AddedRoute, ...] = ()
    routes_wrong: frozenset[tuple[str, str]] = frozenset()
    route_names: dict[tuple[str, str], str] = field(default_factory=dict)
    touchpoints: tuple[Touchpoint, ...] = ()
    merges: dict[str, str] = field(default_factory=dict)
    """Code in the export → the step it is the same as."""
    parallel: dict[str, int] = field(default_factory=dict)
    """Step → machines or places doing the same work under one code (1-20)."""
    step_names: dict[str, str] = field(default_factory=dict)
    step_kinds: dict[str, str] = field(default_factory=dict)


def _kind(text: str) -> ResourceKind:
    try:
        return ResourceKind(text)
    except ValueError:
        return ResourceKind.MACHINE


def apply_flow_edits(plant: LoadedPlant, edits: FlowEdits) -> LoadedPlant:
    """The plant with the client's flow edits, for every calculation."""
    merge = edits.merges

    def code(c: str | None) -> str | None:
        return merge.get(c, c) if c else c

    events = [
        e.model_copy(update={"resource_code": code(e.resource_code)})
        if e.resource_code in merge
        else e
        for e in plant.events
    ]
    resources: list[Resource] = []
    for r in plant.resources:
        if r.resource_code in merge:
            continue
        changes: dict[str, object] = {}
        if r.resource_code in edits.parallel:
            changes["parallel_units"] = edits.parallel[r.resource_code]
        if r.resource_code in edits.step_names:
            changes["name"] = edits.step_names[r.resource_code]
        if r.resource_code in edits.step_kinds:
            changes["kind"] = _kind(edits.step_kinds[r.resource_code])
        resources.append(r.model_copy(update=changes) if changes else r)
    tenant = plant.resources[0].tenant_id if plant.resources else None
    station = plant.resources[0].station_code if plant.resources else None
    for s in edits.steps_added:
        if tenant is None or any(r.resource_code == s.code for r in resources):
            continue
        resources.append(
            Resource(
                tenant_id=tenant,
                resource_code=s.code,
                name=s.name,
                kind=_kind(s.kind),
                station_code=s.station_code or station or s.code,
                parallel_units=edits.parallel.get(s.code, 1),
            )
        )
    calendar = [
        c.model_copy(update={"resource_code": code(c.resource_code)})
        if c.resource_code in merge
        else c
        for c in plant.calendar
    ]
    return replace(plant, events=events, resources=resources, calendar=calendar)


@dataclass(frozen=True)
class EditedArrow:
    from_step: str
    to_step: str
    measured: Arrow | None
    """The arrow as found in the data; None for a route the client added."""
    assumed_jobs: int | None = None
    """Jobs of the route an added step split, expected to pass here (not measured)."""
    assumed_share: Figure | None = None
    estimate_pct: int | None = None
    wrong: bool = False
    hidden: bool = False
    """A measured route replaced by an added step on it."""
    name: str | None = None
    added: bool = False
    route_id: str | None = None


@dataclass(frozen=True)
class EditedFlow:
    found: PlantFlow
    arrows: list[EditedArrow]
    added_steps: list[AddedStep]
    touchpoints: list[Touchpoint]


def edited_flow(flow: PlantFlow, edits: FlowEdits) -> EditedFlow:
    """The flow found in the data with the client's edits laid over it."""
    measured = {(a.from_step, a.to_step): a for a in flow.arrows}
    period = (flow.period_start_at, flow.period_end_at)
    split: dict[tuple[str, str], AddedStep] = {}
    for s in edits.steps_added:
        if s.after and s.before and (s.after, s.before) in measured:
            split.setdefault((s.after, s.before), s)
    out: list[EditedArrow] = []
    for key, found in measured.items():
        out.append(
            EditedArrow(
                found.from_step,
                found.to_step,
                found,
                wrong=key in edits.routes_wrong,
                hidden=key in split,
                name=edits.route_names.get(key),
            )
        )
    for s in edits.steps_added:
        base = measured.get((s.after, s.before)) if s.after and s.before else None
        assumed = (
            base.jobs
            if base is not None and split.get((s.after or "", s.before or "")) == s
            else None
        )
        leaving = sum(m.jobs for m in flow.arrows if m.from_step == s.after)
        for a, b in ((s.after, s.code), (s.code, s.before)):
            if not a or not b:
                continue
            out.append(
                EditedArrow(
                    a,
                    b,
                    None,
                    assumed_jobs=assumed,
                    assumed_share=(
                        flow_share(assumed, leaving if a == s.after else assumed, period)
                        if assumed is not None
                        else None
                    ),
                    wrong=(a, b) in edits.routes_wrong,
                    name=edits.route_names.get((a, b)),
                    added=True,
                )
            )
    for r in edits.routes_added:
        key = (r.from_step, r.to_step)
        if key in measured:
            continue
        out.append(
            EditedArrow(
                r.from_step,
                r.to_step,
                None,
                estimate_pct=r.estimate_pct,
                wrong=key in edits.routes_wrong,
                name=edits.route_names.get(key),
                added=True,
                route_id=r.route_id,
            )
        )
    return EditedFlow(flow, out, list(edits.steps_added), list(edits.touchpoints))
