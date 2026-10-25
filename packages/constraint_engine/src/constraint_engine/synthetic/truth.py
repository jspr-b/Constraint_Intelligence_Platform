"""Ground truth from the generator's own log: true state minutes per machine and month.

Shift time splits exactly into: uncovered breaks + planned maintenance + breakdowns +
available time, and available time into running + setup + blocked + starved. Nothing here
uses engine calculations, so tests against it are not circular.

Steps with several positions, and teams, are counted in position-minutes (ADR-0009): every
staffed position of a shift adds its minutes, and every job's work adds its own minutes.
"""

from datetime import date, time
from typing import Any

from constraint_engine.intervals import Interval, intersect, normalise, subtract, total
from constraint_engine.synthetic.model import SimResult

STATES = (
    "shift_min",
    "break_min",
    "maintenance_min",
    "down_min",
    "running_min",
    "setup_min",
    "blocked_min",
    "starved_min",
    "scrap_run_min",
)


def month_windows(result: SimResult) -> dict[str, Interval]:
    """Calendar months (plant local time) clipped to the history period."""
    out: dict[str, Interval] = {}
    first = result.cfg.start_date.replace(day=1)
    y, m = first.year, first.month
    while True:
        start = result.clock.minute(date(y, m, 1), time(0, 0))
        y2, m2 = (y + 1, 1) if m == 12 else (y, m + 1)
        end = result.clock.minute(date(y2, m2, 1), time(0, 0))
        clipped = (max(start, 0.0), min(end, result.history_end))
        if clipped[0] >= result.history_end:
            return out
        out[f"{y:04d}-{m:02d}"] = clipped
        y, m = y2, m2


def machine_truth(result: SimResult, code: str, window: Interval) -> dict[str, float]:
    cal, log = result.calendars[code], result.logs[code]
    w = [window]
    shift = intersect(cal.shifts, w)
    breaks = intersect(cal.uncovered_breaks(), shift)
    maintenance = intersect(subtract(cal.maintenance, breaks), shift)
    downs = intersect([(s, e) for s, e, reason in log.downs if reason != "PM"], shift)
    available = intersect(result.availability[code], w)
    running = intersect(log.running, w)
    setup = intersect(log.setup, w)
    blocked = subtract(intersect(log.blocked, available), normalise(running + setup))
    starved = total(available) - total(running) - total(setup) - total(blocked)
    scrap = sum(minutes for at, minutes in log.scrap_run_min if window[0] <= at < window[1])
    values = [
        total(shift),
        total(breaks),
        total(maintenance),
        total(downs),
        total(running),
        total(setup),
        total(blocked),
        max(starved, 0.0),
        scrap,
    ]
    return {k: round(v, 3) for k, v in zip(STATES, values, strict=True)}


def pooled(result: SimResult, code: str) -> bool:
    """True for steps counted in positions: several positions, or covered by a team."""
    cfg = result.cfg
    return max(cfg.positions(code)) > 1 or cfg.team_of(code) is not None


def pooled_truth(
    result: SimResult,
    counts: tuple[int, ...],
    cal_code: str,
    running: list[Interval],
    window: Interval,
) -> dict[str, float]:
    """State position-minutes of a step with positions, or of a team, in ``window``."""
    cal, log = result.calendars[cal_code], result.logs[cal_code]
    breaks = cal.uncovered_breaks()
    downs = [(s, e) for s, e, reason in log.downs if reason != "PM"]
    totals = dict.fromkeys(("shift", "break", "maintenance", "down"), 0.0)
    for index, shift in result.shift_windows:
        part = intersect([shift], [window])
        if not part:
            continue
        n = counts[index]
        brk = intersect(breaks, part)
        maint = intersect(subtract(cal.maintenance, brk), part)
        totals["shift"] += n * total(part)
        totals["break"] += n * total(brk)
        totals["maintenance"] += n * total(maint)
        totals["down"] += n * total(intersect(subtract(downs, brk + maint), part))
    available = totals["shift"] - totals["break"] - totals["maintenance"] - totals["down"]
    run = sum(e - s for s, e in (iv for seg in running for iv in intersect([seg], [window])))
    values = {
        "shift_min": totals["shift"],
        "break_min": totals["break"],
        "maintenance_min": totals["maintenance"],
        "down_min": totals["down"],
        "running_min": run,
        "setup_min": 0.0,
        "blocked_min": 0.0,
        "starved_min": max(available - run, 0.0),
        "scrap_run_min": 0.0,
    }
    return {k: round(v, 3) for k, v in values.items()}


def _step_truth(result: SimResult, code: str, window: Interval) -> dict[str, float]:
    if pooled(result, code):
        counts = result.cfg.positions(code)
        return pooled_truth(result, counts, code, result.logs[code].running, window)
    return machine_truth(result, code, window)


def generator_log(result: SimResult) -> dict[str, Any]:
    months = month_windows(result)
    history = (0.0, result.history_end)
    shipped = [o for o in result.orders if o.shipped is not None]
    log: dict[str, Any] = {
        "plant_code": result.cfg.plant_code,
        "seed": result.cfg.seed,
        "history_start_at": result.clock.at(0).isoformat(),
        "history_end_at": result.clock.at(result.history_end).isoformat(),
        "orders_released": sum(1 for o in result.orders if o.arrival is not None),
        "orders_shipped": len(shipped),
        "units_shipped": sum(o.good_quantity for o in shipped),
        "machines": {
            code: {
                "total": _step_truth(result, code, history),
                "months": {m: _step_truth(result, code, w) for m, w in months.items()},
            }
            for code in result.logs
        },
    }
    for team in result.cfg.teams:
        first = team.steps[0]  # the team's steps share the plant calendar
        runs = result.team_logs[team.code].running
        log.setdefault("teams", {})[team.code] = {
            "steps": list(team.steps),
            "total": pooled_truth(result, team.positions, first, runs, history),
            "months": {
                m: pooled_truth(result, team.positions, first, runs, w) for m, w in months.items()
            },
        }
    if result.end_scans:
        log["end_scans_at_handmade_steps"] = dict(sorted(result.end_scans.items()))
        log["forgotten_end_scans"] = dict(sorted(result.forgotten_end_scans.items()))
    return log
