"""Measured facts: every number the pages show about the past, calculated once per import (pure).

One :class:`Fact` is one Figure about one machine (or machine and operation) for one period:
the whole data period (``all``), a local-time month or an ISO week. Families:

- ``state``: minutes per machine state (shift, break, maintenance, down, running, setup,
  blocked, starved, and unknown: time lost events cannot explain)
- ``utilisation``: (running + setup) ÷ available time, in %; unknown time is left out of both
  and lowers confidence, so a few lost events do not change the answer
- ``setup_share``: setup ÷ (running + setup), in %
- ``oee``: availability, performance, quality and OEE (ratios)
- ``effective_capacity``: hours the machine can really produce
- ``queue``: median and P90 time orders wait in front of the machine
- ``wip``: average and highest number of orders waiting in front of the machine
- ``task_time``: median and P90 work minutes per unit per operation (whole period only)
"""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from statistics import median, quantiles

import polars as pl

from constraint_engine.figure import Confidence, Figure, Missing
from constraint_engine.formulas.registry import Calc, Resolved, formula
from constraint_engine.intervals import Interval
from constraint_engine.io.plant_loader import LoadedPlant
from constraint_engine.reconstruct.capacity import machine_oee
from constraint_engine.reconstruct.durations import pair_operations, task_times
from constraint_engine.reconstruct.flow import Flow, reconstruct_flow, wip
from constraint_engine.reconstruct.states import (
    STATES,
    UNKNOWN,
    MachineStates,
    data_end,
    machine_states,
    period_windows,
)
from constraint_engine.reconstruct.timeline import from_min

PeriodKind = str
"""``all``, ``month`` or ``week``."""


@dataclass(frozen=True, slots=True)
class Fact:
    family: str
    subject_code: str
    """The machine (resource code)."""
    measure: str
    """The number's name with its unit suffix, e.g. ``running_min`` or ``availability_ratio``."""
    period_kind: PeriodKind
    figure: Figure
    operation: str | None = None
    """For task times: the operation measured on the machine."""


@dataclass(frozen=True, slots=True)
class Period:
    kind: PeriodKind
    window: Interval

    @property
    def start_at(self) -> datetime:
        return from_min(self.window[0])

    @property
    def end_at(self) -> datetime:
        return from_min(self.window[1])


def _with_period(calc: Calc, period: Period) -> Calc:
    return Calc(
        inputs=calc.inputs,
        compute=calc.compute,
        period_start_at=period.start_at,
        period_end_at=period.end_at,
        confidence_cap=calc.confidence_cap,
    )


@formula(
    "machine_state_min",
    1,
    "minutes of shift time the machine spent in this state, rebuilt from start, end, setup, "
    "down and scan events and the shift calendar",
    unit="min",
)
def state_min(
    resource_code: str,
    state: str,
    minutes: float,
    period: Period,
    blocked_missing: Missing | None,
) -> Calc:
    """Without scans, blocked time is Missing and hidden inside starved (medium confidence)."""

    def compute(i: Resolved) -> float | Missing:
        if state == "blocked" and blocked_missing is not None:
            return blocked_missing
        return round(minutes, 3)

    cap = Confidence.HIGH
    if state == "starved" and blocked_missing is not None:
        cap = blocked_missing.confidence_impact
    if state == UNKNOWN and minutes > 0:
        cap = Confidence.MEDIUM
    return _with_period(
        Calc(
            inputs={"resource_code": resource_code, "state": state},
            compute=compute,
            confidence_cap=cap,
        ),
        period,
    )


@formula(
    "utilisation_pct",
    1,
    "utilisation = (running + setup) ÷ (shift − breaks − maintenance − breakdowns − unknown) × 100",
    unit="pct",
)
def utilisation(states: dict[str, Figure], period: Period) -> Calc:
    def compute(i: Resolved) -> float | Missing:
        available = (
            float(i["shift_min"])
            - float(i["break_min"])
            - float(i["maintenance_min"])
            - float(i["down_min"])
            - float(i["unknown_min"])
        )
        if available <= 0:
            return Missing("available time", "the machine had no available time in the period")
        return round(100 * (float(i["running_min"]) + float(i["setup_min"])) / available, 2)

    keys = ("shift", "break", "maintenance", "down", UNKNOWN, "running", "setup")
    return _with_period(
        Calc(
            inputs={f"{k}_min": states[k] for k in keys},
            compute=compute,
            confidence_cap=_unknown_cap(states),
        ),
        period,
    )


def _unknown_cap(states: dict[str, Figure]) -> Confidence:
    """Some shift time could not be explained (lost events): the share is less certain."""
    unknown = states[UNKNOWN].value
    return (
        Confidence.MEDIUM if isinstance(unknown, int | float) and unknown > 0 else Confidence.HIGH
    )


@formula("setup_share_pct", 1, "setup share = setup ÷ (running + setup) × 100", unit="pct")
def setup_share(states: dict[str, Figure], period: Period) -> Calc:
    def compute(i: Resolved) -> float | Missing:
        busy = float(i["running_min"]) + float(i["setup_min"])
        if busy <= 0:
            return Missing("running time", "the machine did not run in the period")
        return round(100 * float(i["setup_min"]) / busy, 2)

    return _with_period(
        Calc(
            inputs={"setup_min": states["setup"], "running_min": states["running"]},
            compute=compute,
            confidence_cap=_unknown_cap(states),
        ),
        period,
    )


def _queue_inputs(resource_code: str, n: int, has_scans: bool) -> dict[str, str | int]:
    return {
        "resource_code": resource_code,
        "orders_measured": n,
        "arrival_from": "scans at the station" if has_scans else "end of the previous step",
    }


def _wip_inputs(resource_code: str, has_scans: bool) -> dict[str, str | int]:
    inputs = _queue_inputs(resource_code, 0, has_scans)
    del inputs["orders_measured"]
    return inputs


def _queue_cap(n: int, has_scans: bool) -> Confidence:
    return Confidence.HIGH if has_scans and n >= 20 else Confidence.LOW


@formula(
    "queue_time_median_min",
    1,
    "median minutes an order waited in front of the machine, from arrival to start",
    unit="min",
)
def queue_median(
    resource_code: str, values: tuple[float, ...], has_scans: bool, period: Period
) -> Calc:
    def compute(i: Resolved) -> float | Missing:
        if not values:
            return Missing("queue times", "no order started on the machine in the period")
        return round(median(values), 3)

    return _with_period(
        Calc(
            inputs=_queue_inputs(resource_code, len(values), has_scans),
            compute=compute,
            confidence_cap=_queue_cap(len(values), has_scans),
        ),
        period,
    )


@formula(
    "queue_time_p90_min",
    1,
    "90th percentile of minutes an order waited in front of the machine",
    unit="min",
)
def queue_p90(
    resource_code: str, values: tuple[float, ...], has_scans: bool, period: Period
) -> Calc:
    def compute(i: Resolved) -> float | Missing:
        if not values:
            return Missing("queue times", "no order started on the machine in the period")
        return round(quantiles(values, n=10)[-1] if len(values) > 1 else values[0], 3)

    return _with_period(
        Calc(
            inputs=_queue_inputs(resource_code, len(values), has_scans),
            compute=compute,
            confidence_cap=_queue_cap(len(values), has_scans),
        ),
        period,
    )


def _wip_levels(steps: pl.DataFrame, window: Interval) -> tuple[float, int]:
    """Time-weighted average and maximum of a WIP step function within a window."""
    start, end = window
    level, at, area, peak = 0, start, 0.0, 0
    for row in steps.iter_rows(named=True):
        t, new = float(row["at_min"]), int(row["wip"])
        if t <= start:
            level = new
            continue
        if t >= end:
            break
        area += level * (t - at)
        peak = max(peak, level)
        at, level = t, new
    area += level * (end - at)
    peak = max(peak, level)
    return area / (end - start) if end > start else 0.0, peak


@formula(
    "wip_average_units",
    1,
    "average number of orders waiting in front of the machine, weighted by time",
    unit="orders",
)
def wip_average(resource_code: str, average: float, has_scans: bool, period: Period) -> Calc:
    def compute(i: Resolved) -> float:
        return round(average, 3)

    return _with_period(
        Calc(
            inputs=_wip_inputs(resource_code, has_scans),
            compute=compute,
            confidence_cap=Confidence.HIGH if has_scans else Confidence.LOW,
        ),
        period,
    )


@formula(
    "wip_max_units",
    1,
    "highest number of orders waiting in front of the machine at one moment",
    unit="orders",
)
def wip_max(resource_code: str, peak: int, has_scans: bool, period: Period) -> Calc:
    def compute(i: Resolved) -> int:
        return peak

    return _with_period(
        Calc(
            inputs=_wip_inputs(resource_code, has_scans),
            compute=compute,
            confidence_cap=Confidence.HIGH if has_scans else Confidence.LOW,
        ),
        period,
    )


def periods(plant: LoadedPlant, states: dict[str, MachineStates]) -> list[Period]:
    """The whole data period, then each local-time month and ISO week in it."""
    starts = [s for ms in states.values() for s, _ in ms.shift[:1]]
    if not starts:
        return []
    window = (min(starts), data_end(plant))
    if window[1] <= window[0]:
        return []
    tz = "UTC" if isinstance(plant.plant, Missing) else plant.plant.timezone_iana
    out = [Period("all", window)]
    for kind, freq in (("month", "M"), ("week", "W")):
        for w in period_windows(from_min(window[0]), from_min(window[1]), tz, freq).values():
            clipped = (max(w[0], window[0]), min(w[1], window[1]))
            if clipped[1] > clipped[0]:
                out.append(Period(kind, clipped))
    return out


def _machine_facts(code: str, ms: MachineStates, period: Period, flow: Flow) -> Iterator[Fact]:
    minutes = ms.minutes(period.window)
    figs: dict[str, Figure] = {}
    for state in ("shift", *STATES, UNKNOWN):
        figs[state] = state_min(code, state, minutes[state], period, ms.blocked_missing)
        yield Fact("state", code, f"{state}_min", period.kind, figs[state])
    yield Fact("utilisation", code, "utilisation_pct", period.kind, utilisation(figs, period))
    yield Fact("setup_share", code, "setup_share_pct", period.kind, setup_share(figs, period))

    stays = (
        flow.queue_stays.filter(pl.col("resource_code") == code)
        if not flow.queue_stays.is_empty()
        else flow.queue_stays
    )
    start, end = period.window
    values = tuple(
        float(r["queue_min"])
        for r in stays.iter_rows(named=True)
        if start <= float(r["started_min"]) < end
    )
    yield Fact(
        "queue",
        code,
        "queue_median_min",
        period.kind,
        queue_median(code, values, flow.has_scans, period),
    )
    yield Fact(
        "queue",
        code,
        "queue_p90_min",
        period.kind,
        queue_p90(code, values, flow.has_scans, period),
    )
    steps = (
        wip(flow, code)
        if not flow.queue_stays.is_empty()
        else pl.DataFrame(schema={"at_min": pl.Float64, "wip": pl.Int64})
    )
    average, peak = _wip_levels(steps, period.window)
    yield Fact(
        "wip",
        code,
        "wip_average_units",
        period.kind,
        wip_average(code, average, flow.has_scans, period),
    )
    yield Fact(
        "wip", code, "wip_max_units", period.kind, wip_max(code, peak, flow.has_scans, period)
    )


def measured_facts(plant: LoadedPlant) -> list[Fact]:
    """Every measured fact for every machine and period. Pure: same plant, same facts."""
    ops = pair_operations(plant)
    states = machine_states(plant, ops)
    flow = reconstruct_flow(plant, ops)
    out: list[Fact] = []
    spans = periods(plant, states)
    for period in spans:
        for code in sorted(states):
            out.extend(_machine_facts(code, states[code], period, flow))
        for code, m in sorted(machine_oee(plant, period.window, ops).items()):
            for measure, fig in (
                ("availability_ratio", m.availability),
                ("performance_ratio", m.performance),
                ("quality_ratio", m.quality),
                ("oee_ratio", m.oee),
            ):
                out.append(Fact("oee", code, measure, period.kind, _periodised(fig, period)))
            out.append(
                Fact(
                    "effective_capacity",
                    code,
                    "effective_capacity_h",
                    period.kind,
                    _periodised(m.effective_capacity_h, period),
                )
            )
    if not spans:
        return out
    whole = spans[0]
    for t in task_times(ops, per_product=False):
        out.append(
            Fact(
                "task_time",
                t.resource_code,
                "median_min_per_unit",
                "all",
                _periodised(t.median_min_per_unit, whole),
                t.operation,
            )
        )
        out.append(
            Fact(
                "task_time",
                t.resource_code,
                "p90_min_per_unit",
                "all",
                _periodised(t.p90_min_per_unit, whole),
                t.operation,
            )
        )
    return out


def _periodised(fig: Figure, period: Period) -> Figure:
    """OEE Figures carry no period of their own; stamp the window they were calculated for."""
    return Figure(
        value=fig.value,
        unit=fig.unit,
        formula_id=fig.formula_id,
        inputs=fig.inputs,
        period_start_at=period.start_at,
        period_end_at=period.end_at,
        confidence=fig.confidence,
    )
