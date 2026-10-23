"""Pair events into operations and setups, and measure task times (pure)."""

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from statistics import median, quantiles

import polars as pl

from cip_schema.transactional import EventType, OperationEvent
from constraint_engine.figure import Confidence, Figure, Missing
from constraint_engine.formulas.registry import Calc, Resolved, formula
from constraint_engine.intervals import CoverageIndex
from constraint_engine.io.plant_loader import LoadedPlant
from constraint_engine.reconstruct.timeline import machine_time, to_min

JobKey = tuple[str, str | None, int | None]


@dataclass(frozen=True, slots=True)
class Unpaired:
    event: OperationEvent
    missing: Missing


@dataclass
class Operations:
    jobs: pl.DataFrame
    """One row per completed operation: resource_code, order_id, operation_seq, sku, operation,
    quantity_units, start_at, end_at, wall_min, work_min, work_min_per_unit."""
    setups: pl.DataFrame
    """resource_code, start_at, end_at, wall_min, work_min."""
    unpaired: list[Unpaired]


def _operation_names(plant: LoadedPlant) -> dict[tuple[str, int], tuple[str, str]]:
    """(order, operation_seq) -> (sku, operation name), from the order's routing."""
    by_sku: dict[str, dict[int, str]] = defaultdict(dict)
    for r in plant.routings:
        for step in r.steps:
            by_sku[r.sku][step.operation_seq] = step.operation
    return {
        (o.order_id, seq): (o.sku, name)
        for o in plant.orders
        if o.sku is not None
        for seq, name in by_sku[o.sku].items()
    }


def _work(index: CoverageIndex | None, start: datetime, end: datetime) -> float:
    """Minutes the machine was available between start and end (breaks, nights, stops excluded)."""
    a, b = to_min(start), to_min(end)
    return index.covered(a, b) if index else b - a


def _latest_starts(plant: LoadedPlant) -> dict[str, OperationEvent]:
    latest: dict[str, OperationEvent] = {}
    for e in plant.events:
        if e.event_type is EventType.START and e.resource_code is not None:
            current = latest.get(e.resource_code)
            if current is None or (e.at, e.event_id) > (current.at, current.event_id):
                latest[e.resource_code] = e
    return latest


def _job_row(
    start: OperationEvent,
    end: OperationEvent,
    work: float,
    names: dict[tuple[str, int], tuple[str, str]],
) -> dict[str, object]:
    sku, operation = names.get((end.order_id or "", end.operation_seq or 0), (None, None))
    qty = end.quantity_units or start.quantity_units
    return {
        "resource_code": end.resource_code,
        "order_id": end.order_id,
        "operation_seq": end.operation_seq,
        "sku": sku,
        "operation": operation,
        "quantity_units": qty,
        "start_at": start.at,
        "end_at": end.at,
        "wall_min": to_min(end.at) - to_min(start.at),
        "work_min": work,
        "work_min_per_unit": work / qty if qty else None,
    }


def pair_operations(plant: LoadedPlant) -> Operations:
    times = {code: CoverageIndex(mt.available) for code, mt in machine_time(plant).items()}
    names = _operation_names(plant)
    open_jobs: dict[JobKey, deque[OperationEvent]] = defaultdict(deque)
    open_setups: dict[str, OperationEvent] = {}
    jobs: list[dict[str, object]] = []
    setups: list[dict[str, object]] = []
    unpaired: list[Unpaired] = []
    for e in sorted(plant.events, key=lambda e: (e.at, e.event_id)):
        code = e.resource_code
        if code is None:
            continue
        key = (code, e.order_id, e.operation_seq)
        if e.event_type is EventType.START:
            open_jobs[key].append(e)
        elif e.event_type is EventType.END:
            if not open_jobs[key]:
                missing = Missing("start", "end event without a start", Confidence.MEDIUM)
                unpaired.append(Unpaired(e, missing))
                continue
            start = open_jobs[key].popleft()
            jobs.append(_job_row(start, e, _work(times.get(code), start.at, e.at), names))
        elif e.event_type is EventType.SETUP_START:
            open_setups[code] = e
        elif e.event_type is EventType.SETUP_END and code in open_setups:
            start = open_setups.pop(code)
            setups.append(
                {
                    "resource_code": code,
                    "start_at": start.at,
                    "end_at": e.at,
                    "wall_min": to_min(e.at) - to_min(start.at),
                    "work_min": _work(times.get(code), start.at, e.at),
                }
            )
    latest = _latest_starts(plant)
    for queue in open_jobs.values():
        for start in queue:
            running = start.resource_code is not None and latest.get(start.resource_code) is start
            reason = (
                "still running at the end of the data" if running else "start event without an end"
            )
            impact = Confidence.NONE if running else Confidence.MEDIUM
            unpaired.append(Unpaired(start, Missing("end", reason, impact)))
    return Operations(pl.DataFrame(jobs), pl.DataFrame(setups), unpaired)


def _stats_inputs(values: tuple[float, ...], resource: str, label: str) -> dict[str, str | int]:
    return {"resource_code": resource, "operation": label, "operations_measured": len(values)}


def _cap(values: tuple[float, ...]) -> Confidence:
    return Confidence.HIGH if len(values) >= 20 else Confidence.LOW


@formula(
    "task_time_median",
    1,
    "median of measured work minutes per unit over completed operations",
    unit="min_per_unit",
)
def _median(values: tuple[float, ...], resource: str, label: str) -> Calc:
    def compute(i: Resolved) -> float:
        return round(median(values), 4)

    return Calc(
        inputs=_stats_inputs(values, resource, label), compute=compute, confidence_cap=_cap(values)
    )


@formula(
    "task_time_p90", 1, "90th percentile of measured work minutes per unit", unit="min_per_unit"
)
def _p90(values: tuple[float, ...], resource: str, label: str) -> Calc:
    def compute(i: Resolved) -> float:
        return round(quantiles(values, n=10)[-1] if len(values) > 1 else values[0], 4)

    return Calc(
        inputs=_stats_inputs(values, resource, label), compute=compute, confidence_cap=_cap(values)
    )


@dataclass(frozen=True, slots=True)
class TaskTime:
    resource_code: str
    operation: str
    sku: str | None
    """None when times are pooled over all products."""
    median_min_per_unit: Figure
    p90_min_per_unit: Figure


def task_times(ops: Operations, per_product: bool = True) -> list[TaskTime]:
    """Median and P90 per machine and operation, and per product unless pooled.

    Multi-purpose machines are split per operation. The same operation usually takes a
    different time per product, so per-product times are the default.
    """
    if ops.jobs.is_empty():
        return []
    keys = ["resource_code", "operation", "sku"] if per_product else ["resource_code", "operation"]
    grouped = (
        ops.jobs.filter(
            pl.col("work_min_per_unit").is_not_null() & pl.col("operation").is_not_null()
        )
        .group_by(keys)
        .agg(pl.col("work_min_per_unit"))
        .sort(keys)
    )
    out = []
    for row in grouped.iter_rows(named=True):
        values = tuple(row["work_min_per_unit"])
        sku = row.get("sku")
        label = f"{row['operation']} ({sku})" if per_product else row["operation"]
        out.append(
            TaskTime(
                row["resource_code"],
                row["operation"],
                sku,
                _median(values, row["resource_code"], label),
                _p90(values, row["resource_code"], label),
            )
        )
    return out
