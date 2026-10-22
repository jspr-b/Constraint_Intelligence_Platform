"""Lost throughput: where the bottleneck's time goes, and what it costs (pure).

Only bottleneck time converts to output (CLAUDE.md, Domain model), so loss is measured on the
period's detected constraint only:

- lost hours per cause = the bottleneck's minutes in that state ÷ 60, for breakdowns, setup,
  starved, blocked, uncovered breaks and planned maintenance; plus scrap: bottleneck minutes
  spent on units scrapped at or after the bottleneck
- throughput per bottleneck hour for the product mix = Σ (units × (sales price − truly variable
  cost)) ÷ Σ bottleneck work hours, over the orders the bottleneck finished in the period
- lost € = lost hours × throughput per bottleneck hour

A period without an internal constraint (market or material bound) has no bottleneck loss.
Results are :class:`~constraint_engine.facts.Fact` rows (families ``loss`` and ``throughput``),
stored with the measured facts.
"""

from collections.abc import Sequence
from datetime import datetime

import polars as pl

from constraint_engine.detection import Detection
from constraint_engine.facts import Fact, Period
from constraint_engine.figure import Confidence, Figure, Missing
from constraint_engine.formulas.registry import Calc, Resolved, formula
from constraint_engine.io.plant_loader import LoadedPlant
from constraint_engine.reconstruct.durations import Operations, pair_operations
from constraint_engine.reconstruct.timeline import to_min

CAUSES: tuple[tuple[str, str], ...] = (
    ("breakdowns", "down"),
    ("setup", "setup"),
    ("starved", "starved"),
    ("blocked", "blocked"),
    ("breaks", "break"),
    ("maintenance", "maintenance"),
)
"""(cause, machine state) pairs; scrap is added separately."""
ALL_CAUSES = (*(c for c, _ in CAUSES), "scrap")

NO_PRICES = Missing(
    what="sales prices",
    reason="no products with a sales price and truly variable cost: add the products export "
    "(item master with prices) to see euros",
    confidence_impact=Confidence.NONE,
)


@formula(
    "lost_constraint_h",
    1,
    "hours the bottleneck did not produce for this cause = its minutes for the cause ÷ 60",
    unit="h",
)
def lost_hours(cause: str, minutes: Figure, period: Period) -> Calc:
    def compute(i: Resolved) -> float:
        return round(float(i["minutes"]) / 60, 3)

    return Calc(
        inputs={"cause": cause, "minutes": minutes},
        compute=compute,
        period_start_at=period.start_at,
        period_end_at=period.end_at,
    )


@formula(
    "scrap_constraint_min",
    1,
    "bottleneck minutes lost to scrap = Σ units scrapped at or after the bottleneck × the "
    "bottleneck's work minutes per unit on that order",
    unit="min",
)
def scrap_minutes(
    resource_code: str, units: int, events: int, minutes: float, period: Period
) -> Calc:
    return Calc(
        inputs={
            "resource_code": resource_code,
            "scrapped_units": units,
            "scrap_events": events,
            "bottleneck_work_min": round(minutes, 3),
        },
        compute=lambda i: round(float(i["bottleneck_work_min"]), 3),
        period_start_at=period.start_at,
        period_end_at=period.end_at,
    )


@formula("lost_constraint_h_total", 1, "all hours the bottleneck lost = sum of the causes", "h")
def lost_total(causes: dict[str, Figure], period: Period) -> Calc:
    def compute(i: Resolved) -> float:
        return round(sum(float(i[c]) for c in causes), 3)

    return Calc(
        inputs=dict(causes),
        compute=compute,
        period_start_at=period.start_at,
        period_end_at=period.end_at,
    )


@formula(
    "throughput_per_constraint_h",
    1,
    "throughput per bottleneck hour = Σ (units × (sales price − truly variable cost)) ÷ Σ "
    "bottleneck work hours, over the orders the bottleneck finished",
    unit="eur_cents_per_h",
)
def throughput_rate(
    resource_code: str,
    sku: str | None,
    throughput_eur_cents: int,
    work_min: float,
    units: int,
    unpriced_units: int,
    priced: bool,
    period: Period,
) -> Calc:
    """For the product mix (``sku`` None) or one product. Units without a price are left out."""

    def compute(i: Resolved) -> float | Missing:
        minutes = float(i["bottleneck_work_min"])
        if minutes <= 0:
            return Missing(
                "bottleneck work time",
                "the bottleneck finished no priced orders in the period",
                Confidence.NONE,
            )
        return round(int(i["throughput_eur_cents"]) / (minutes / 60), 2)

    inputs: dict[str, Figure | Missing | int | float | str] = {
        "resource_code": resource_code,
        "throughput_eur_cents": throughput_eur_cents if priced else NO_PRICES,
        "bottleneck_work_min": round(work_min, 3),
        "units": units,
    }
    if sku:
        inputs["sku"] = sku
    if unpriced_units:
        inputs["units_without_price"] = unpriced_units
    return Calc(
        inputs=inputs,
        compute=compute,
        period_start_at=period.start_at,
        period_end_at=period.end_at,
        confidence_cap=Confidence.MEDIUM if unpriced_units else Confidence.HIGH,
    )


@formula(
    "lost_throughput_eur_cents",
    1,
    "lost throughput = lost bottleneck hours × throughput per bottleneck hour",
    unit="eur_cents",
)
def lost_euros(hours: Figure, rate: Figure) -> Calc:
    return Calc(
        inputs={"lost_h": hours, "throughput_per_constraint_h_eur_cents": rate},
        compute=lambda i: round(
            float(i["lost_h"]) * float(i["throughput_per_constraint_h_eur_cents"])
        ),
        period_start_at=hours.period_start_at,
        period_end_at=hours.period_end_at,
    )


def _jobs(ops: Operations, code: str, lo: datetime, hi: datetime) -> pl.DataFrame:
    jobs = ops.jobs.filter(pl.col("resource_code") == code)
    return jobs.filter((pl.col("end_at") >= lo) & (pl.col("end_at") < hi))


def _rates(
    plant: LoadedPlant, ops: Operations, code: str, period: Period, per_product: bool
) -> list[tuple[str | None, Figure]]:
    prices = {
        p.sku: p.sales_price_eur_cents - p.truly_variable_cost_eur_cents for p in plant.products
    }
    jobs = _jobs(ops, code, period.start_at, period.end_at)

    def rate(rows: pl.DataFrame, sku: str | None) -> Figure:
        priced = rows.filter(pl.col("sku").is_in(list(prices)))
        unpriced = int(rows.filter(~pl.col("sku").is_in(list(prices)))["quantity_units"].sum())
        throughput = sum(
            prices[r["sku"]] * int(r["quantity_units"]) for r in priced.iter_rows(named=True)
        )
        return throughput_rate(
            code,
            sku,
            int(throughput),
            float(priced["work_min"].sum()),
            int(priced["quantity_units"].sum()),
            unpriced,
            bool(prices),
            period,
        )

    out: list[tuple[str | None, Figure]] = [(None, rate(jobs, None))]
    if per_product:
        for sku in sorted(set(jobs["sku"].to_list()) & set(prices)):
            out.append((sku, rate(jobs.filter(pl.col("sku") == sku), sku)))
    return out


def _scrap(plant: LoadedPlant, ops: Operations, code: str, period: Period) -> Figure:
    """Bottleneck minutes spent on units later scrapped (or scrapped at the bottleneck)."""
    at_bottleneck = {
        r["order_id"]: (int(r["operation_seq"]), float(r["work_min_per_unit"]))
        for r in ops.jobs.filter(pl.col("resource_code") == code).iter_rows(named=True)
    }
    units = events = 0
    minutes = 0.0
    for e in plant.events:
        if e.event_type.value != "scrap" or not e.scrap_units or e.order_id not in at_bottleneck:
            continue
        if not period.window[0] <= to_min(e.at) < period.window[1]:
            continue
        seq, per_unit = at_bottleneck[e.order_id]
        if e.operation_seq is not None and e.operation_seq < seq:
            continue  # scrapped before it reached the bottleneck: no bottleneck time lost
        units += e.scrap_units
        events += 1
        minutes += e.scrap_units * per_unit
    return scrap_minutes(code, units, events, minutes, period)


def loss_facts(
    plant: LoadedPlant,
    facts: Sequence[Fact],
    detections: Sequence[tuple[str, Detection]],
    ops: Operations | None = None,
) -> list[Fact]:
    """Bottleneck loss in hours and € for every period with an internal constraint."""
    ops = ops or pair_operations(plant)
    states = {
        (f.period_kind, f.figure.period_start_at, f.subject_code, f.measure): f.figure
        for f in facts
        if f.family == "state"
    }
    out: list[Fact] = []
    for kind, d in detections:
        code = d.resource_code
        if code is None or d.kind != "internal" or not (d.period_start_at and d.period_end_at):
            continue
        period = Period(kind, (to_min(d.period_start_at), to_min(d.period_end_at)))
        hours: dict[str, Figure] = {}
        for cause, state in CAUSES:
            minutes = states.get((kind, d.period_start_at, code, f"{state}_min"))
            if minutes is not None:
                hours[cause] = lost_hours(cause, minutes, period)
        hours["scrap"] = lost_hours("scrap", _scrap(plant, ops, code, period), period)
        total = lost_total(hours, period)
        rates = _rates(plant, ops, code, period, per_product=kind == "all")
        mix = rates[0][1]
        for sku, fig in rates:
            out.append(
                Fact(
                    "throughput",
                    code,
                    "throughput_per_constraint_h_eur_cents",
                    kind,
                    fig,
                    reason_code=sku,
                )
            )
        for cause, fig in [*hours.items(), ("total", total)]:
            out.append(Fact("loss", code, "lost_h", kind, fig, reason_code=cause))
            out.append(
                Fact("loss", code, "lost_eur_cents", kind, lost_euros(fig, mix), reason_code=cause)
            )
    return out
