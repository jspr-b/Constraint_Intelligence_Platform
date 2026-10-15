"""Effective capacity and OEE per machine, as Figures (pure).

OEE is an input to finding the constraint, not a goal on its own (CLAUDE.md): a starved or
blocked machine shows low performance, and that is expected away from the constraint.

- Planned production time P = shifts − uncovered breaks − planned maintenance
- Availability A = (P − unplanned stops) / P
- Performance = Σ(ideal minutes per unit × units processed) / (P − unplanned stops); ideal = ERP
  standard run time per unit; when missing, the measured time per unit (confidence low)
- Quality Q = (units processed − scrap found at the machine) / units processed
- OEE = A × Performance × Q
- Effective capacity = P × A (hours the machine can really produce)
"""

from dataclasses import dataclass

from cip_schema.transactional import EventType
from constraint_engine.figure import Confidence, Figure, Missing
from constraint_engine.formulas.registry import Calc, Resolved, formula
from constraint_engine.intervals import Interval, intersect, total
from constraint_engine.io.plant_loader import LoadedPlant
from constraint_engine.reconstruct.durations import Operations, pair_operations
from constraint_engine.reconstruct.timeline import machine_time, to_min


@formula(
    "oee_availability",
    1,
    "availability = (planned production − unplanned stops) ÷ planned production",
    unit="ratio",
)
def availability(planned_min: float, stop_min: float) -> Calc:
    def compute(i: Resolved) -> float | Missing:
        p = float(i["planned_production_min"])
        if p <= 0:
            return Missing("planned_production_min", "no planned production time in the period")
        return round((p - float(i["unplanned_stop_min"])) / p, 4)

    return Calc(
        inputs={
            "planned_production_min": round(planned_min, 3),
            "unplanned_stop_min": round(stop_min, 3),
        },
        compute=compute,
    )


@formula(
    "oee_performance",
    1,
    "performance = Σ(ideal min per unit × units) ÷ (planned production − stops)",
    unit="ratio",
)
def performance(ideal_min: float, run_min: float, ideal_source: str) -> Calc:
    def compute(i: Resolved) -> float | Missing:
        run = float(i["run_time_min"])
        if run <= 0:
            return Missing("run_time_min", "no run time in the period")
        return round(float(i["ideal_min"]) / run, 4)

    cap = Confidence.HIGH if ideal_source == "erp_standard" else Confidence.LOW
    return Calc(
        inputs={
            "ideal_min": round(ideal_min, 3),
            "run_time_min": round(run_min, 3),
            "ideal_source": ideal_source,
        },
        compute=compute,
        confidence_cap=cap,
    )


@formula(
    "oee_quality",
    1,
    "quality = (units processed − scrap found at the machine) ÷ units processed",
    unit="ratio",
)
def quality(units: int, scrap: int) -> Calc:
    def compute(i: Resolved) -> float | Missing:
        n = int(i["units_processed"])
        if n == 0:
            return Missing("units_processed", "no units processed in the period")
        return round((n - int(i["scrap_units"])) / n, 4)

    return Calc(inputs={"units_processed": units, "scrap_units": scrap}, compute=compute)


@formula("oee", 1, "OEE = availability × performance × quality", unit="ratio")
def oee(a: Figure, p: Figure, q: Figure) -> Calc:
    def compute(i: Resolved) -> float:
        return round(float(i["availability"]) * float(i["performance"]) * float(i["quality"]), 4)

    return Calc(inputs={"availability": a, "performance": p, "quality": q}, compute=compute)


@formula(
    "effective_capacity_h",
    1,
    "effective capacity = planned production hours × availability",
    unit="h",
)
def effective_capacity_h(planned_min: float, a: Figure) -> Calc:
    def compute(i: Resolved) -> float:
        return round(float(i["planned_production_min"]) / 60 * float(i["availability"]), 3)

    return Calc(
        inputs={"planned_production_min": round(planned_min, 3), "availability": a}, compute=compute
    )


@dataclass(frozen=True, slots=True)
class MachineOee:
    resource_code: str
    availability: Figure
    performance: Figure
    quality: Figure
    oee: Figure
    effective_capacity_h: Figure


def _ideal(plant: LoadedPlant) -> dict[tuple[str, str, int], float]:
    """(sku, resource, seq) -> ERP standard run minutes per unit."""
    return {
        (r.sku, s.resource_code, s.operation_seq): s.standard_run_min_per_unit
        for r in plant.routings
        for s in r.steps
        if s.standard_run_min_per_unit is not None
    }


def machine_oee(
    plant: LoadedPlant, window: Interval | None = None, ops: Operations | None = None
) -> dict[str, MachineOee]:
    ops = ops or pair_operations(plant)
    times = machine_time(plant)
    ideal_std = _ideal(plant)
    w = [window] if window else None
    out = {}
    for code, mt in times.items():
        planned = total(intersect(mt.production, w) if w else mt.production)
        stops = total(intersect(mt.stops, w) if w else mt.stops)
        jobs = (
            ops.jobs.filter(ops.jobs["resource_code"] == code)
            if not ops.jobs.is_empty()
            else ops.jobs
        )
        units, ideal_min, source = 0, 0.0, "erp_standard"
        for row in jobs.iter_rows(named=True):
            if w and not (w[0][0] <= to_min(row["end_at"]) < w[0][1]):
                continue
            qty = int(row["quantity_units"] or 0)
            std = ideal_std.get((row["sku"], code, row["operation_seq"]))
            if std is None:
                std, source = (row["work_min_per_unit"] or 0.0), "measured"
            units += qty
            ideal_min += std * qty
        scrap = sum(
            e.scrap_units
            for e in plant.events
            if e.event_type is EventType.SCRAP
            and e.resource_code == code
            and (not w or w[0][0] <= to_min(e.at) < w[0][1])
        )
        a = availability(planned, stops)
        p = performance(ideal_min, planned - stops, source)
        q = quality(units, scrap)
        out[code] = MachineOee(code, a, p, q, oee(a, p, q), effective_capacity_h(planned, a))
    return out
