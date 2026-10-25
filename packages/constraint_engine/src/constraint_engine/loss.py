"""Lost throughput: where the bottleneck's time goes, and what it costs (pure).

Only bottleneck time converts to output (CLAUDE.md, Domain model), so loss is measured on the
period's detected constraint only:

- lost hours per cause = the bottleneck's minutes in that state ÷ 60, for breakdowns, setup,
  starved, blocked, uncovered breaks and planned maintenance; plus scrap: bottleneck minutes
  spent on units scrapped at or after the bottleneck
- throughput per bottleneck hour for the product mix = Σ (units × (sales price − truly variable
  cost)) ÷ Σ bottleneck work hours, over the orders the bottleneck finished in the period
- without products, per job (ADR-0009): (job value − material cost), spread over the job's
  bottleneck work, ÷ bottleneck work hours (``job_throughput_per_constraint_h``); a job whose
  product has a price uses the product; a job with neither counts as without a price, and with
  no priced job at all there is no euro figure, only hours
- lost € = lost hours × throughput per bottleneck hour

When the bottleneck is a shared team, its work is the work at the steps it covers and its hours
are position-hours (staffed positions × hours).

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
from constraint_engine.reconstruct.durations import NO_END, Operations, pair_operations
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
    reason="no products with a sales price and truly variable cost, and no jobs with a value "
    "and material cost: add the products export (item master with prices) or job values to see "
    "euros",
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
    "job_throughput_per_constraint_h",
    1,
    "throughput per bottleneck hour = Σ money ÷ Σ bottleneck work hours over the jobs the "
    "bottleneck worked on; money per job = units × (sales price − truly variable cost) when its "
    "product has both, else (job value − material cost) × the share of the job's bottleneck "
    "work in the period; jobs with a forgotten scan at the bottleneck are left out",
    unit="eur_cents_per_h",
)
def job_throughput_rate(
    resource_code: str,
    from_products_eur_cents: int,
    from_jobs_eur_cents: int,
    work_min: float,
    jobs: int,
    jobs_without_value: int,
    period: Period,
) -> Calc:
    def compute(i: Resolved) -> float | Missing:
        minutes = float(i["bottleneck_work_min"])
        if minutes <= 0:
            return Missing(
                "bottleneck work time",
                "the bottleneck worked on no job with a price or value in the period",
                Confidence.NONE,
            )
        money = int(i["from_products_eur_cents"]) + int(i["from_job_values_eur_cents"])
        return round(money / (minutes / 60), 2)

    inputs: dict[str, Figure | Missing | int | float | str] = {
        "resource_code": resource_code,
        "from_products_eur_cents": from_products_eur_cents,
        "from_job_values_eur_cents": from_jobs_eur_cents,
        "bottleneck_work_min": round(work_min, 3),
        "jobs": jobs,
    }
    if jobs_without_value:
        inputs["jobs_without_value"] = jobs_without_value
    return Calc(
        inputs=inputs,
        compute=compute,
        period_start_at=period.start_at,
        period_end_at=period.end_at,
        confidence_cap=Confidence.MEDIUM if jobs_without_value else Confidence.HIGH,
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


def _jobs(ops: Operations, codes: Sequence[str], lo: datetime, hi: datetime) -> pl.DataFrame:
    jobs = ops.jobs.filter(pl.col("resource_code").is_in(list(codes)))
    return jobs.filter((pl.col("end_at") >= lo) & (pl.col("end_at") < hi))


def _job_rate(
    plant: LoadedPlant,
    ops: Operations,
    code: str,
    codes: Sequence[str],
    jobs: pl.DataFrame,
    prices: dict[str, int],
    period: Period,
) -> Figure:
    """Money per bottleneck hour from products where priced, else from job value (ADR-0009)."""
    values = {
        o.order_id: o.order_value_eur_cents - o.material_cost_eur_cents
        for o in plant.orders
        if o.order_value_eur_cents is not None and o.material_cost_eur_cents is not None
    }
    # A job with a forgotten scan at the bottleneck has unknown bottleneck work: left out.
    gaps = {
        u.event.order_id
        for u in ops.unpaired
        if u.missing.reason == NO_END and u.event.resource_code in codes
    }
    at_bottleneck = ops.jobs.filter(pl.col("resource_code").is_in(list(codes)))
    work_per_job: dict[str, float] = {}
    for r in at_bottleneck.iter_rows(named=True):
        work_per_job[r["order_id"]] = work_per_job.get(r["order_id"], 0.0) + float(r["work_min"])
    products = from_jobs = 0.0
    minutes, seen, without = 0.0, set(), set()
    for r in jobs.iter_rows(named=True):
        order, work = r["order_id"], float(r["work_min"])
        if order in gaps:
            continue
        if r["sku"] in prices:
            products += prices[r["sku"]] * int(r["quantity_units"])
        elif order in values and work_per_job.get(order):
            from_jobs += values[order] * work / work_per_job[order]
        else:
            without.add(order)
            continue
        minutes += work
        seen.add(order)
    return job_throughput_rate(
        code, round(products), round(from_jobs), minutes, len(seen), len(without - seen), period
    )


def _rates(
    plant: LoadedPlant,
    ops: Operations,
    code: str,
    period: Period,
    per_product: bool,
    covers: Sequence[str] = (),
) -> list[tuple[str | None, Figure]]:
    prices = {
        p.sku: p.sales_price_eur_cents - p.truly_variable_cost_eur_cents for p in plant.products
    }
    codes = covers or (code,)
    jobs = _jobs(ops, codes, period.start_at, period.end_at)
    if any(o.order_value_eur_cents is not None for o in plant.orders) and (
        not prices or jobs.filter(~pl.col("sku").is_in(list(prices))).height
    ):
        return [(None, _job_rate(plant, ops, code, codes, jobs, prices, period))]

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


def _scrap(
    plant: LoadedPlant, ops: Operations, code: str, period: Period, covers: Sequence[str] = ()
) -> Figure:
    """Bottleneck minutes spent on units later scrapped (or scrapped at the bottleneck).

    A scrap before the job reached the bottleneck costs no bottleneck time: by step number when
    both have one, otherwise by time (ADR-0009: jobs without step numbers)."""
    at_bottleneck: dict[str, tuple[int | None, float, float]] = {}
    rows = ops.jobs.filter(pl.col("resource_code").is_in(list(covers or (code,))))
    for r in rows.sort("start_at").iter_rows(named=True):
        per_unit = float(r["work_min_per_unit"] or 0.0)
        if r["order_id"] in at_bottleneck:  # a team: the job's work at all its steps
            seq, start, before = at_bottleneck[r["order_id"]]
            at_bottleneck[r["order_id"]] = (seq, start, before + per_unit)
        else:
            at_bottleneck[r["order_id"]] = (r["operation_seq"], to_min(r["start_at"]), per_unit)
    units = events = 0
    minutes = 0.0
    for e in plant.events:
        if e.event_type.value != "scrap" or not e.scrap_units or e.order_id not in at_bottleneck:
            continue
        if not period.window[0] <= to_min(e.at) < period.window[1]:
            continue
        seq, start_min, per_unit = at_bottleneck[e.order_id]
        if e.operation_seq is not None and seq is not None:
            before = e.operation_seq < seq
        else:
            before = to_min(e.at) < start_min
        if before:
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
        scrap = _scrap(plant, ops, code, period, d.covers)
        hours["scrap"] = lost_hours("scrap", scrap, period)
        total = lost_total(hours, period)
        rates = _rates(plant, ops, code, period, per_product=kind == "all", covers=d.covers)
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
