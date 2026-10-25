"""Queues, transitions and touchpoints: where orders wait (pure).

Queue in front of a machine: from the order's arrival (scan/move at the machine's station)
until its job starts there. Without scans, the previous job's end is used as arrival, so
transport and queue time cannot be told apart.

A job's steps follow its routing step numbers. Jobs without step numbers (ADR-0009) take the
path from history: their steps in the order of their start times (``path_from_history``).
"""

from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass

import polars as pl

from cip_schema.transactional import EventType, OperationEvent
from constraint_engine.io.plant_loader import LoadedPlant
from constraint_engine.reconstruct.durations import Operations, pair_operations
from constraint_engine.reconstruct.timeline import to_min


@dataclass
class Flow:
    queue_stays: pl.DataFrame
    """resource_code, order_id, operation_seq, arrived_min, started_min, queue_min."""
    transitions: pl.DataFrame
    """order_id, from_resource, to_resource, from_seq, to_seq, end_min, arrived_min, start_min,
    transport_min, queue_min, setup_min, wait_min (= transport + queue + setup)."""
    has_scans: bool
    path_from_history: bool = False
    """True when some job's path came from its touchpoint times, not from step numbers."""


def _arrivals(plant: LoadedPlant) -> dict[str, list[float]]:
    out: dict[str, list[float]] = defaultdict(list)
    for e in plant.events:
        if e.event_type in (EventType.SCAN, EventType.MOVE) and e.order_id:
            out[e.order_id].append(to_min(e.at))
    return {k: sorted(v) for k, v in out.items()}


def _setup_starts(ops: Operations) -> dict[tuple[str, float], float]:
    """(machine, setup end) -> setup start: a job after a setup left the queue at setup start."""
    if ops.setups.is_empty():
        return {}
    return {
        (row["resource_code"], round(to_min(row["end_at"]), 6)): to_min(row["start_at"])
        for row in ops.setups.iter_rows(named=True)
    }


def reconstruct_flow(plant: LoadedPlant, ops: Operations | None = None) -> Flow:
    ops = ops or pair_operations(plant)
    arrivals = _arrivals(plant)
    setup_start = _setup_starts(ops)
    has_scans = bool(arrivals)
    if ops.jobs.is_empty():
        return Flow(pl.DataFrame(), pl.DataFrame(), has_scans)
    history = ops.jobs["operation_seq"].null_count() > 0
    jobs = ops.jobs.sort("order_id", "operation_seq", "start_at").iter_rows(named=True)
    by_order: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in jobs:
        by_order[str(row["order_id"])].append(row)
    stays, transitions = [], []
    for order_id, rows in by_order.items():
        scans = arrivals.get(order_id, [])
        prev_end: float | None = None
        prev: dict[str, object] | None = None
        for row in rows:
            start = to_min(row["start_at"])  # type: ignore[arg-type]
            on_machine = setup_start.get((str(row["resource_code"]), round(start, 6)), start)
            i = bisect_right(scans, on_machine) - 1
            arrived = (
                scans[i] if i >= 0 and (prev_end is None or scans[i] >= prev_end) else prev_end
            )
            if arrived is not None:
                stays.append(
                    {
                        "resource_code": row["resource_code"],
                        "order_id": order_id,
                        "operation_seq": row["operation_seq"],
                        "arrived_min": arrived,
                        "started_min": on_machine,
                        "queue_min": on_machine - arrived,
                    }
                )
            if prev is not None and prev_end is not None:
                arr = arrived if arrived is not None else prev_end
                transitions.append(
                    {
                        "order_id": order_id,
                        "from_resource": prev["resource_code"],
                        "to_resource": row["resource_code"],
                        "from_seq": prev["operation_seq"],
                        "to_seq": row["operation_seq"],
                        "end_min": prev_end,
                        "arrived_min": arr,
                        "start_min": start,
                        "transport_min": arr - prev_end,
                        "queue_min": on_machine - arr,
                        "setup_min": start - on_machine,
                        "wait_min": start - prev_end,
                    }
                )
            prev, prev_end = row, to_min(row["end_at"])  # type: ignore[arg-type]
    return Flow(pl.DataFrame(stays), pl.DataFrame(transitions), has_scans, history)


def wip(flow: Flow, resource_code: str, covers: tuple[str, ...] = ()) -> pl.DataFrame:
    """Orders waiting in front of a machine over time: columns at_min, wip (step function).
    For a team (``covers``): orders waiting in front of any of its steps.

    All arrivals and starts at the same moment are applied together, so a start and an
    arrival in the same minute never show a level that did not exist.
    """
    stays = flow.queue_stays.filter(pl.col("resource_code").is_in(covers or (resource_code,)))
    change: dict[float, int] = defaultdict(int)
    for at in stays["arrived_min"]:
        change[at] += 1
    for at in stays["started_min"]:
        change[at] -= 1
    level, rows = 0, []
    for at in sorted(change):
        level += change[at]
        rows.append({"at_min": at, "wip": level})
    return pl.DataFrame(rows, schema={"at_min": pl.Float64, "wip": pl.Int64})


def touchpoints(plant: LoadedPlant, order_id: str) -> list[OperationEvent]:
    """Every event of one order, in time order (scans by station, never by person)."""
    return sorted(
        (e for e in plant.events if e.order_id == order_id), key=lambda e: (e.at, e.event_id)
    )
