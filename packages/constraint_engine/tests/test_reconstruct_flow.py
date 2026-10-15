"""Queues and transitions on plant A."""

from pathlib import Path

import polars as pl
import pytest

from constraint_engine.io.plant_loader import load_plant
from constraint_engine.reconstruct.durations import pair_operations
from constraint_engine.reconstruct.flow import reconstruct_flow, touchpoints, wip
from constraint_engine.reconstruct.timeline import to_min
from constraint_engine.synthetic.config import load_config

DATA = Path(__file__).resolve().parents[3] / "data" / "synthetic"


@pytest.fixture(scope="module")
def plant():  # type: ignore[no-untyped-def]
    return load_plant(DATA / "plant_a")


@pytest.fixture(scope="module")
def ops(plant):  # type: ignore[no-untyped-def]
    return pair_operations(plant)


@pytest.fixture(scope="module")
def flow(plant, ops):  # type: ignore[no-untyped-def]
    return reconstruct_flow(plant, ops)


def test_queue_before_paint_respects_buffer_and_is_full(flow) -> None:  # type: ignore[no-untyped-def]
    capacity = next(
        r for r in load_config(DATA / "plant_a" / "config.yaml").resources if r.code == "PNT-01"
    ).buffer_orders
    levels: list[int] = wip(flow, "PNT-01")["wip"].to_list()
    assert max(levels) <= capacity
    assert min(levels) >= 0
    assert sum(levels) / len(levels) > capacity / 2  # the constraint's queue is mostly full


def test_paint_queue_is_the_longest_wait(flow) -> None:  # type: ignore[no-untyped-def]
    mean_queue = (
        flow.queue_stays.group_by("resource_code").agg(pl.col("queue_min").mean()).sort("queue_min")
    )
    assert mean_queue["resource_code"][-1] == "PNT-01"


def test_lead_time_is_processing_plus_waiting(plant, ops, flow) -> None:  # type: ignore[no-untyped-def]
    shipped = {o.order_id: o for o in plant.orders if o.shipped_at and o.released_at}
    jobs = ops.jobs.group_by("order_id").agg(pl.col("wall_min").sum(), pl.col("start_at").min())
    waits = flow.transitions.group_by("order_id").agg(pl.col("wait_min").sum())
    w = dict(zip(waits["order_id"], waits["wait_min"], strict=True))
    checked = 0
    for oid, wall, first_start in jobs.iter_rows():
        order = shipped.get(oid)
        if order is None:
            continue
        lead = to_min(order.shipped_at) - to_min(order.released_at)
        first_wait = to_min(first_start) - to_min(order.released_at)
        assert first_wait + wall + w.get(oid, 0.0) == pytest.approx(lead, abs=0.1)
        checked += 1
    assert checked > 300


def test_transport_queue_and_setup_make_up_the_wait(flow) -> None:  # type: ignore[no-untyped-def]
    t = flow.transitions
    parts = t["transport_min"] + t["queue_min"] + t["setup_min"]
    assert ((parts - t["wait_min"]).abs() < 1e-6).all()
    assert (t["queue_min"] >= -1e-6).all() and (t["setup_min"] >= -1e-6).all()
    assert flow.has_scans


def test_touchpoints_are_every_event_of_the_order(plant) -> None:  # type: ignore[no-untyped-def]
    order = next(o for o in plant.orders if o.shipped_at)
    points = touchpoints(plant, order.order_id)
    assert len(points) == sum(1 for e in plant.events if e.order_id == order.order_id)
    assert points == sorted(points, key=lambda e: (e.at, e.event_id))
