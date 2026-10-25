"""Known answers for a synthetic plant, from its config and the generator's own log.

Nothing here calls engine calculations: answers come from how the data was generated, so
pillar tests that compare engine output to these answers are not circular.
"""

from datetime import timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from constraint_engine.intervals import Interval, intersect, subtract, total
from constraint_engine.synthetic.model import SimResult
from constraint_engine.synthetic.truth import generator_log, month_windows, pooled

BINDING_LOAD_PCT = 85.0
"""Below this utilisation everywhere, no machine is treated as binding (market-bound)."""


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LostHours(_M):
    breaks_h: float
    setup_h: float
    starved_h: float
    blocked_h: float
    breakdowns_h: float
    maintenance_h: float
    scrap_h: float


class ForecastWeek(_M):
    orderbook_week: int = Field(ge=1)
    iso_week: str
    load_pct: dict[str, float]
    binding_resource: str | None


class ExpectedAnswers(_M):
    plant_code: str
    seed: int
    constraint: str | Literal["none"]
    constraint_kind: Literal["internal", "market"]
    utilisation_pct: dict[str, float]
    throughput_eur_cents_per_constraint_h: dict[str, float | None]
    lost_constraint_h_by_month: dict[str, LostHours]
    forecast: list[ForecastWeek]
    constraint_moves: dict[str, Any] | None
    # Plants with teams or handmade steps only (ADR-0009); left out of A, B and C's file.
    constraint_type: Literal["step", "team"] | None = None
    constraint_covers: list[str] | None = None
    forgotten_end_scan_share_pct: float | None = None
    throughput_eur_cents_per_constraint_h_by_month: dict[str, float] | None = None


def _utilisation(log: dict[str, Any]) -> dict[str, float]:
    out = {}
    for code, machine in {**log["machines"], **log.get("teams", {})}.items():
        t = machine["total"]
        available = t["shift_min"] - t["break_min"] - t["maintenance_min"] - t["down_min"]
        out[code] = (
            round(100 * (t["running_min"] + t["setup_min"]) / available, 2) if available else 0.0
        )
    return out


def _lost_hours(month: dict[str, float]) -> LostHours:
    return LostHours(
        breaks_h=round(month["break_min"] / 60, 3),
        setup_h=round(month["setup_min"] / 60, 3),
        starved_h=round(month["starved_min"] / 60, 3),
        blocked_h=round(month["blocked_min"] / 60, 3),
        breakdowns_h=round(month["down_min"] / 60, 3),
        maintenance_h=round(month["maintenance_min"] / 60, 3),
        scrap_h=round(month["scrap_run_min"] / 60, 3),
    )


def _staffed_min(
    result: SimResult, counts: tuple[int, ...], production: list[Interval], start: float
) -> float:
    """Staffed position-minutes of production time in the week starting at ``start``."""
    week = [(start, start + 7 * 1440.0)]
    return sum(
        counts[i] * total(intersect(intersect(production, [shift]), week))
        for i, shift in result.shift_windows
    )


def _job_throughput_per_team_h(result: SimResult, team: str) -> float | None:
    """Jobs' value minus material per position-hour they used at the team's steps.

    Only shipped jobs count; a job's value is quantity × its type's price (generator truth)."""
    shipped = [o for o in result.orders if o.shipped is not None and o.team_run_min > 0]
    minutes = sum(o.team_run_min for o in shipped)
    money = sum(o.quantity * (o.product.price_eur_cents - o.product.tvc_eur_cents) for o in shipped)
    return round(money / minutes * 60, 2) if minutes else None


def _job_throughput_by_month(result: SimResult) -> dict[str, float]:
    """Per month: jobs' value minus material, each spread over its team work, per team hour
    worked in the month. All jobs that used the team count, shipped or not."""
    out = {}
    for month, window in month_windows(result).items():
        money = minutes = 0.0
        for o in result.orders:
            worked = sum(e - s for s, e in o.team_segments)
            if not worked:
                continue
            inside = sum(e - s for s, e in intersect(o.team_segments, [window]))
            margin = o.quantity * (o.product.price_eur_cents - o.product.tvc_eur_cents)
            money += margin * inside / worked
            minutes += inside
        if minutes:
            out[month] = round(money / minutes * 60, 2)
    return out


def _forecast(result: SimResult) -> list[ForecastWeek]:
    """Load per machine per order-book week: run plus setup minutes / available minutes.

    Available = shifts minus uncovered breaks minus planned maintenance (random breakdowns are
    not forecast).
    """
    cfg, week = result.cfg, 7 * 1440.0
    weeks: list[ForecastWeek] = []
    for n in range(1, cfg.weeks_orderbook + 1):
        start = result.history_end + (n - 1) * week
        window = [(start, start + week)]
        demand: dict[str, float] = {r.code: 0.0 for r in cfg.resources}
        for order in result.orders:
            created = order.due - order.product.due_days * 1440
            if order.arrival is None and start <= created < start + week:
                for step in order.product.steps:
                    # Each order is counted with one setup where the step needs setups:
                    # with five colour families nearly every paint order changes colour.
                    demand[step.resource] += step.run_min_per_unit * order.quantity + step.setup_min
        load = {}
        for code, cal in result.calendars.items():
            production = subtract(subtract(cal.shifts, cal.uncovered_breaks()), cal.maintenance)
            if pooled(result, code):
                available = _staffed_min(result, cfg.positions(code), production, start)
            else:
                available = total(intersect(production, window))
            load[code] = round(100 * demand[code] / available, 2) if available else 0.0
        for team in cfg.teams:
            cal = result.calendars[team.steps[0]]
            production = subtract(subtract(cal.shifts, cal.uncovered_breaks()), cal.maintenance)
            available = _staffed_min(result, team.positions, production, start)
            needed = sum(demand[step] for step in team.steps)
            load[team.code] = round(100 * needed / available, 2) if available else 0.0
        top = max(load, key=lambda c: load[c])
        iso = (cfg.start_date + timedelta(weeks=cfg.weeks_history + n - 1)).isocalendar()
        weeks.append(
            ForecastWeek(
                orderbook_week=n,
                iso_week=f"{iso.year}-W{iso.week:02d}",
                load_pct=load,
                binding_resource=top if load[top] >= BINDING_LOAD_PCT else None,
            )
        )
    return weeks


def expected_answers(result: SimResult) -> ExpectedAnswers:
    log = generator_log(result)
    util = _utilisation(log)
    top = max(util, key=lambda c: util[c])
    internal = util[top] >= BINDING_LOAD_PCT
    constraint = top if internal else "none"
    teams = log.get("teams", {})
    throughput: dict[str, float | None] = {}
    if not result.cfg.export.products:
        throughput["jobs"] = _job_throughput_per_team_h(result, top) if top in teams else None
    else:
        for p in result.cfg.products:
            minutes = sum(s.run_min_per_unit for s in p.steps if s.resource == top)
            tpu = p.price_eur_cents - p.tvc_eur_cents
            throughput[p.sku] = round(tpu / minutes * 60, 2) if internal and minutes else None
    months = (teams.get(top) or log["machines"][top])["months"]
    lost = {m: _lost_hours(v) for m, v in months.items()} if internal else {}
    forecast = _forecast(result)
    moves = next(
        (
            {"orderbook_week": w.orderbook_week, "iso_week": w.iso_week, "to": w.binding_resource}
            for w in forecast
            if w.binding_resource is not None and w.binding_resource != constraint
        ),
        None,
    )
    return ExpectedAnswers(
        plant_code=result.cfg.plant_code,
        seed=result.cfg.seed,
        constraint=constraint,
        constraint_kind="internal" if internal else "market",
        utilisation_pct=util,
        throughput_eur_cents_per_constraint_h=throughput,
        lost_constraint_h_by_month=lost,
        forecast=forecast,
        constraint_moves=moves,
        **_steps_extras(result, log, top),
    )


def _steps_extras(result: SimResult, log: dict[str, Any], top: str) -> dict[str, Any]:
    """Answers that only plants with teams or handmade steps have."""
    if not (result.cfg.teams or result.end_scans):
        return {}
    teams = log.get("teams", {})
    scans = sum(result.end_scans.values())
    forgotten = sum(result.forgotten_end_scans.values())
    return {
        "constraint_type": "team" if top in teams else "step",
        "constraint_covers": teams[top]["steps"] if top in teams else None,
        "forgotten_end_scan_share_pct": round(100 * forgotten / scans, 2) if scans else None,
        "throughput_eur_cents_per_constraint_h_by_month": (
            _job_throughput_by_month(result)
            if top in teams and not result.cfg.export.products
            else None
        ),
    }
