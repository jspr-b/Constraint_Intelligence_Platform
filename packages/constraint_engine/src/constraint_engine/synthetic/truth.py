"""Ground truth from the generator's own log: true state minutes per machine and month.

Shift time splits exactly into: uncovered breaks + planned maintenance + breakdowns +
available time, and available time into running + setup + blocked + starved. Nothing here
uses engine calculations, so tests against it are not circular.
"""

from datetime import date, time
from typing import Any

from constraint_engine.synthetic.intervals import Interval, intersect, normalise, subtract, total
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


def generator_log(result: SimResult) -> dict[str, Any]:
    months = month_windows(result)
    history = (0.0, result.history_end)
    shipped = [o for o in result.orders if o.shipped is not None]
    return {
        "plant_code": result.cfg.plant_code,
        "seed": result.cfg.seed,
        "history_start_at": result.clock.at(0).isoformat(),
        "history_end_at": result.clock.at(result.history_end).isoformat(),
        "orders_released": sum(1 for o in result.orders if o.arrival is not None),
        "orders_shipped": len(shipped),
        "units_shipped": sum(o.good_quantity for o in shipped),
        "machines": {
            code: {
                "total": machine_truth(result, code, history),
                "months": {m: machine_truth(result, code, w) for m, w in months.items()},
            }
            for code in result.logs
        },
    }
