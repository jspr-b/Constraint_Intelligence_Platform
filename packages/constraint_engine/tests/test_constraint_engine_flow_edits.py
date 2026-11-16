"""The client's flow edits: what the engine calculates on, and what the client sees."""

import uuid
from datetime import UTC, datetime, timedelta

from cip_schema.master import Resource, ResourceKind
from cip_schema.transactional import EventType, OperationEvent
from constraint_engine.figure import Missing
from constraint_engine.flow_edits import (
    AddedRoute,
    AddedStep,
    FlowEdits,
    apply_flow_edits,
    edited_flow,
)
from constraint_engine.io.plant_loader import LoadedPlant
from constraint_engine.reconstruct.routes import plant_flow

TENANT = uuid.UUID(int=1)
T0 = datetime(2026, 3, 2, 6, tzinfo=UTC)


def _plant(paths: dict[str, list[str]]) -> LoadedPlant:
    events = []
    codes: set[str] = set()
    for job, steps in paths.items():
        for i, step in enumerate(steps):
            codes.add(step)
            for kind, h in (("start", 2 * i), ("end", 2 * i + 1)):
                events.append(
                    OperationEvent(
                        tenant_id=TENANT,
                        event_id=f"{job}-{i}-{kind}",
                        event_type=EventType(kind),
                        at=T0 + timedelta(hours=h),
                        resource_code=step,
                        order_id=job,
                    )
                )
    resources = [
        Resource(tenant_id=TENANT, resource_code=c, name=c, station_code="ST-" + c)
        for c in sorted(codes)
    ]
    return LoadedPlant(plant=Missing("plant", "test"), events=events, resources=resources)


PLANT = _plant({"J1": ["CUT", "WLD", "PNT"], "J2": ["CUT", "WLD-OLD", "PNT"], "J3": ["CUT", "PNT"]})


def test_no_edits_change_nothing() -> None:
    assert apply_flow_edits(PLANT, FlowEdits()) == PLANT


def test_a_merged_code_becomes_the_same_step() -> None:
    plant = apply_flow_edits(PLANT, FlowEdits(merges={"WLD-OLD": "WLD"}))
    assert "WLD-OLD" not in {r.resource_code for r in plant.resources}
    assert "WLD-OLD" not in {e.resource_code for e in plant.events}
    flow = plant_flow(plant)
    assert (flow.routes[0].steps, flow.routes[0].jobs) == (("CUT", "WLD", "PNT"), 2)


def test_parallel_places_set_capacity_and_names_and_kinds_change() -> None:
    plant = apply_flow_edits(
        PLANT,
        FlowEdits(
            parallel={"PNT": 3}, step_names={"PNT": "Paint line"}, step_kinds={"CUT": "check"}
        ),
    )
    by = {r.resource_code: r for r in plant.resources}
    assert by["PNT"].parallel_units == 3 and by["PNT"].name == "Paint line"
    assert by["CUT"].kind is ResourceKind.CHECK


def test_an_added_step_exists_without_data() -> None:
    step = AddedStep("NEW-01", "Visual check", "check", None, "WLD", "PNT")
    plant = apply_flow_edits(PLANT, FlowEdits(steps_added=(step,)))
    assert "NEW-01" in {r.resource_code for r in plant.resources}
    assert "NEW-01" not in {e.resource_code for e in plant.events}  # nothing invented


def test_an_added_step_on_a_route_takes_its_jobs_as_assumed() -> None:
    flow = plant_flow(PLANT)
    step = AddedStep("NEW-01", "Visual check", "check", None, "WLD", "PNT")
    view = edited_flow(flow, FlowEdits(steps_added=(step,)))
    by = {(a.from_step, a.to_step): a for a in view.arrows}
    assert by[("WLD", "PNT")].hidden  # the original route is replaced, not deleted
    into = by[("WLD", "NEW-01")]
    assert into.measured is None and into.added and into.assumed_jobs == 1
    assert into.assumed_share is not None and into.assumed_share.inputs["jobs_this_way"] == 1


def test_wrong_routes_names_and_estimates_are_kept_apart() -> None:
    flow = plant_flow(PLANT)
    view = edited_flow(
        flow,
        FlowEdits(
            routes_wrong=frozenset({("CUT", "PNT")}),
            route_names={("CUT", "WLD"): "Main line"},
            routes_added=(AddedRoute("r1", "WLD", "CUT", estimate_pct=20),),
        ),
    )
    by = {(a.from_step, a.to_step): a for a in view.arrows}
    assert by[("CUT", "PNT")].wrong and by[("CUT", "PNT")].measured is not None
    assert by[("CUT", "WLD")].name == "Main line"
    added = by[("WLD", "CUT")]
    assert added.estimate_pct == 20 and added.measured is None and added.assumed_jobs is None
