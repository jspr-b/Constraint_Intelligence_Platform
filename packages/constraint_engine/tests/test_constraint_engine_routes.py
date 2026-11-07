"""The plant's flow found from touchpoints, on tiny plants with known answers."""

import uuid
from datetime import UTC, datetime, timedelta

from cip_schema.transactional import EventType, OperationEvent
from constraint_engine.figure import Missing
from constraint_engine.io.plant_loader import LoadedPlant
from constraint_engine.reconstruct.routes import plant_flow

TENANT = uuid.UUID(int=1)
Visits = dict[str, list[tuple[str, int, int | None]]]
T0 = datetime(2026, 3, 2, 6, tzinfo=UTC)


def _plant(paths: Visits) -> LoadedPlant:
    """Per job its visits as (step, start hour, end hour or None)."""
    events: list[OperationEvent] = []
    for job, visits in paths.items():
        for step, start, end in visits:
            for kind, h in (("start", start), ("end", end)):
                if h is None:
                    continue
                events.append(
                    OperationEvent(
                        tenant_id=TENANT,
                        event_id=f"{job}-{step}-{kind}-{h}",
                        event_type=EventType(kind),
                        at=T0 + timedelta(hours=h),
                        resource_code=step,
                        order_id=job,
                    )
                )
    return LoadedPlant(plant=Missing("plant", "test"), events=events)


def test_routes_and_shares_are_counted_from_start_order() -> None:
    flow = plant_flow(
        _plant(
            {
                "J1": [("CUT", 0, 1), ("WLD", 2, 3), ("PNT", 4, 5)],
                "J2": [("CUT", 0, 1), ("WLD", 2, 3), ("PNT", 4, 5)],
                "J3": [("CUT", 0, 1), ("WLD", 2, 3), ("PNT", 4, 5)],
                "J4": [("CUT", 0, 1), ("PNT", 2, 3)],
            }
        )
    )
    assert flow.jobs == 4
    assert [(r.steps, r.jobs, r.share.value) for r in flow.routes] == [
        (("CUT", "WLD", "PNT"), 3, 75.0),
        (("CUT", "PNT"), 1, 25.0),
    ]
    arrows = {(a.from_step, a.to_step): a for a in flow.arrows}
    assert arrows[("CUT", "WLD")].share.value == 75.0  # of the 4 jobs leaving CUT
    assert arrows[("CUT", "PNT")].share.value == 25.0
    assert arrows[("WLD", "PNT")].share.value == 100.0
    assert not any(a.less_certain for a in flow.arrows)
    share = flow.routes[0].share
    assert share.formula_id.startswith("flow_share_pct")
    assert share.period_start_at == T0  # every share says its period and inputs


def test_a_restart_is_one_visit_and_a_return_is_rework() -> None:
    flow = plant_flow(
        _plant(
            {
                "J1": [("CUT", 0, None), ("CUT", 1, 2), ("WLD", 3, 4), ("CUT", 5, 6)],
            }
        )
    )
    route = flow.routes[0]
    assert route.steps == ("CUT", "WLD", "CUT")
    assert route.rework and route.less_certain
    back = next(a for a in flow.arrows if a.to_step == "CUT")
    assert back.rework and back.less_certain


def test_missing_finish_and_parallel_steps_are_less_certain() -> None:
    flow = plant_flow(
        _plant(
            {
                "J1": [("CUT", 0, None), ("WLD", 2, 3)],  # forgot to scan out of CUT
                "J2": [("CUT", 0, 3), ("WLD", 1, 4)],  # at two steps at once
            }
        )
    )
    arrow = flow.arrows[0]
    assert (arrow.from_step, arrow.to_step, arrow.uncertain_jobs) == ("CUT", "WLD", 2)
    assert arrow.less_certain
    assert flow.overlapping_jobs == 1
    assert next(s for s in flow.steps if s.code == "CUT").missing_finish == 1


def test_routes_beyond_the_top_ones_are_counted_together() -> None:
    steps = ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"]
    paths: Visits = {f"J{i}": [(steps[i], 0, 1), ("ZZ", 2, 3)] for i in range(8)}
    flow = plant_flow(_plant(paths))
    assert len(flow.routes) == 6
    assert flow.other_routes_jobs == 2
    assert flow.jobs == 8


def test_no_touchpoints_is_an_empty_flow() -> None:
    flow = plant_flow(LoadedPlant(plant=Missing("plant", "test")))
    assert (flow.jobs, flow.routes, flow.arrows) == (0, [], [])
    assert flow.period_start_at is None
