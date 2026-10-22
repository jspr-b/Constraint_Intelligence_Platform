"""Constraint detection: several independent methods, then one answer with agreement (pure).

CLAUDE.md detection rules: never rely on one method; output confidence and the data behind it;
use effective (measured) capacity; and say so when no machine is binding (market or material).

Methods, each a registered formula with its own Figure:

- ``utilisation``: the busiest machine on measured available time; binding at 85 % or more.
- ``queue``: the machine with the most orders waiting in front of it; binding at 1 order or more
  on average.
- ``active_period``: the machine that is most often the one running longest without a break in
  its work (the active period method); binding when it is so 75 % of the time or more.
- ``starved_blocked``: the machine that is least often starved or blocked; binding when that is
  10 % of its shift time or less.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from constraint_engine.figure import Confidence, Figure, Missing, weakest
from constraint_engine.formulas.registry import Calc, Resolved, formula
from constraint_engine.intervals import Interval, normalise
from constraint_engine.io.plant_loader import LoadedPlant
from constraint_engine.reconstruct.states import UNKNOWN, MachineStates
from constraint_engine.reconstruct.timeline import from_min

if TYPE_CHECKING:
    from constraint_engine.facts import Fact

BINDING_UTILISATION_PCT = 85.0
BINDING_WIP_ORDERS = 1.0
BINDING_ACTIVE_SHARE_PCT = 75.0
BINDING_IDLE_SHARE_PCT = 10.0
MATERIAL_SHARE_PCT = 20.0

METHODS = ("utilisation", "queue", "active_period", "starved_blocked")
NONE = "none"


@dataclass(frozen=True, slots=True)
class Reason:
    """A plain-word reason, as a message code with values (the UI holds the words)."""

    code: str
    values: Mapping[str, str | int | float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MethodResult:
    method: str
    resource_code: str | None
    """The machine this method points at, or None when it finds no binding machine."""
    evidence: Figure
    """The method's own number for that machine (or for the top machine when none binds)."""
    top_code: str | None
    """The top machine by this method, binding or not."""


@dataclass(frozen=True, slots=True)
class Detection:
    resource_code: str | None
    """The constraint, or None when no machine limits output."""
    kind: str
    """``internal`` (a machine), ``market`` (orders) or ``material``."""
    agreement: Figure
    confidence: Confidence
    reasons: tuple[Reason, ...]
    """Plain-word reasons for the answer and its confidence (codes the UI translates)."""
    methods: tuple[MethodResult, ...] = field(default_factory=tuple)
    period_start_at: datetime | None = None
    period_end_at: datetime | None = None


def _key(code: str, measure: str) -> str:
    return f"{code}_{measure}"


def _numeric(fig: Figure) -> float | None:
    return None if isinstance(fig.value, Missing) else float(fig.value)


def _top(figs: Mapping[str, Figure], lowest: bool = False) -> str | None:
    known = {c: v for c, f in figs.items() if (v := _numeric(f)) is not None}
    if not known:
        return None
    return (min if lowest else max)(sorted(known), key=lambda c: known[c])


def _pick(i: Resolved, lowest: bool = False) -> float | Missing:
    values = [float(v) for v in i.values() if isinstance(v, int | float)]
    if not values:
        return Missing("machines", "no machine has this number in the period")
    return round(min(values) if lowest else max(values), 2)


@formula(
    "constraint_by_utilisation",
    1,
    "the busiest machine on measured available time; binding at 85 % busy or more",
    unit="pct",
)
def by_utilisation(busy: Mapping[str, Figure], window: tuple[datetime, datetime]) -> Calc:
    return Calc(
        inputs={_key(c, "utilisation_pct"): f for c, f in sorted(busy.items())},
        compute=_pick,
        period_start_at=window[0],
        period_end_at=window[1],
    )


@formula(
    "constraint_by_queue",
    1,
    "the machine with the most orders waiting in front of it; binding at 1 order or more on "
    "average",
    unit="orders",
)
def by_queue(waiting: Mapping[str, Figure], window: tuple[datetime, datetime]) -> Calc:
    return Calc(
        inputs={_key(c, "wip_average_units"): f for c, f in sorted(waiting.items())},
        compute=_pick,
        period_start_at=window[0],
        period_end_at=window[1],
    )


@formula(
    "active_period_share_pct",
    1,
    "share of the time this machine was the one working longest without a break in its work "
    "(running, setup or a breakdown), among all machines working at that moment",
    unit="pct",
)
def active_share(
    code: str, minutes: float, total_min: float, window: tuple[datetime, datetime]
) -> Calc:
    def compute(i: Resolved) -> float | Missing:
        if float(i["working_min"]) <= 0:
            return Missing("working time", "no machine worked in the period")
        return round(100 * float(i["longest_active_min"]) / float(i["working_min"]), 2)

    return Calc(
        inputs={
            "resource_code": code,
            "longest_active_min": round(minutes, 3),
            "working_min": round(total_min, 3),
        },
        compute=compute,
        period_start_at=window[0],
        period_end_at=window[1],
    )


@formula(
    "constraint_by_active_period",
    1,
    "the machine that is most often the one working longest without a break; binding when it "
    "is so 75 % of the time or more",
    unit="pct",
)
def by_active_period(shares: Mapping[str, Figure], window: tuple[datetime, datetime]) -> Calc:
    return Calc(
        inputs={_key(c, "active_share_pct"): f for c, f in sorted(shares.items())},
        compute=_pick,
        period_start_at=window[0],
        period_end_at=window[1],
    )


@formula(
    "idle_share_pct",
    1,
    "idle share = starved + blocked, as a share of shift time",
    unit="pct",
)
def idle_share(starved: Figure, blocked: Figure, window: tuple[datetime, datetime]) -> Calc:
    """Without scans blocked time is Missing and already inside starved: starved alone, medium."""
    no_scans = isinstance(blocked.value, Missing)
    inputs: dict[str, Figure | str] = {"starved_pct": starved}
    if not no_scans:
        inputs["blocked_pct"] = blocked

    def compute(i: Resolved) -> float:
        return round(float(i["starved_pct"]) + float(i.get("blocked_pct", 0.0)), 2)

    return Calc(
        inputs=inputs,
        compute=compute,
        period_start_at=window[0],
        period_end_at=window[1],
        confidence_cap=Confidence.MEDIUM if no_scans else Confidence.HIGH,
    )


@formula(
    "constraint_by_starved_blocked",
    1,
    "the machine least often starved or blocked; binding when that is 10 % of its shift time "
    "or less",
    unit="pct",
)
def by_starved_blocked(idle: Mapping[str, Figure], window: tuple[datetime, datetime]) -> Calc:
    return Calc(
        inputs={_key(c, "idle_share_pct"): f for c, f in sorted(idle.items())},
        compute=lambda i: _pick(i, lowest=True),
        period_start_at=window[0],
        period_end_at=window[1],
    )


@formula(
    "constraint_agreement_pct",
    1,
    "agreement = methods that point at the answer ÷ methods run × 100",
    unit="pct",
)
def agreement(picks: Mapping[str, str], answer: str, window: tuple[datetime, datetime]) -> Calc:
    def compute(i: Resolved) -> float:
        return round(100 * sum(1 for m in METHODS if i[m] == answer) / len(METHODS), 1)

    return Calc(
        inputs={**{m: picks[m] for m in METHODS}, "answer": answer},
        compute=compute,
        period_start_at=window[0],
        period_end_at=window[1],
    )


@formula(
    "material_late_share_pct",
    1,
    "share of released orders whose material arrived after release",
    unit="pct",
)
def material_late(late: int, released: int, window: tuple[datetime, datetime]) -> Calc:
    def compute(i: Resolved) -> float | Missing:
        if int(i["orders_released"]) == 0:
            return Missing("orders", "no released orders with a material date in the period")
        return round(100 * int(i["orders_material_late"]) / int(i["orders_released"]), 1)

    return Calc(
        inputs={"orders_material_late": late, "orders_released": released},
        compute=compute,
        period_start_at=window[0],
        period_end_at=window[1],
    )


def active_period_minutes(
    states: Mapping[str, MachineStates], window: Interval
) -> tuple[dict[str, float], float]:
    """Minutes each machine was the one with the longest active period, and the working total.

    Active = running, setup or a breakdown (or time the data cannot explain). Breaks and
    planned maintenance inside an active stretch neither end nor extend it.
    """
    periods: list[tuple[float, float, str]] = []
    for code, ms in states.items():
        active = normalise(
            [iv for s in ("running", "setup", "down", UNKNOWN) for iv in ms.intervals.get(s, [])]
        )
        pauses = normalise(ms.intervals.get("break", []) + ms.intervals.get("maintenance", []))
        touching = [p for p in pauses if any(a <= p[1] and p[0] <= b for a, b in active)]
        for start, end in normalise(active + touching):
            periods.append((start, end, code))
    events = sorted(
        [(s, 1, i) for i, (s, _, _) in enumerate(periods)]
        + [(e, 0, i) for i, (_, e, _) in enumerate(periods)]
    )
    out = dict.fromkeys(states, 0.0)
    total, live, last = 0.0, set[int](), None
    lo, hi = window
    for t, kind, i in events:
        if last is not None and live and t > last:
            a, b = max(last, lo), min(t, hi)
            if b > a:
                best = max(sorted(live), key=lambda j: periods[j][1] - periods[j][0])
                out[periods[best][2]] += b - a
                total += b - a
        if kind == 1:
            live.add(i)
        else:
            live.discard(i)
        last = t
    return out, total


def _material(plant: LoadedPlant, lo: datetime, hi: datetime) -> Figure:
    released = [
        o
        for o in plant.orders
        if o.released_at is not None
        and o.material_ready_at is not None
        and lo <= o.released_at < hi
    ]
    late = sum(
        1
        for o in released
        if o.material_ready_at and o.released_at and o.material_ready_at > o.released_at
    )
    return material_late(late, len(released), (lo, hi))


def detect(
    plant: LoadedPlant,
    states: Mapping[str, MachineStates],
    window: Interval,
    busy: Mapping[str, Figure],
    waiting: Mapping[str, Figure],
    starved: Mapping[str, Figure],
    blocked: Mapping[str, Figure],
    gap_impacts: Sequence[Confidence] = (),
) -> Detection:
    """One answer for one period from the four methods (inputs are the period's facts)."""
    span = (from_min(window[0]), from_min(window[1]))
    minutes, total = active_period_minutes(states, window)
    shares = {c: active_share(c, m, total, span) for c, m in sorted(minutes.items())}
    idle = {c: idle_share(starved[c], blocked[c], span) for c in sorted(starved) if c in blocked}

    def result(
        method: str, fig: Figure, figs: Mapping[str, Figure], binds: bool, lowest: bool = False
    ) -> MethodResult:
        top = _top(figs, lowest)
        return MethodResult(method, top if binds and top else None, fig, top)

    u = by_utilisation(busy, span)
    q = by_queue(waiting, span)
    a = by_active_period(shares, span)
    s = by_starved_blocked(idle, span)
    results = (
        result("utilisation", u, busy, (_numeric(u) or 0) >= BINDING_UTILISATION_PCT),
        result("queue", q, waiting, (_numeric(q) or 0) >= BINDING_WIP_ORDERS),
        result("active_period", a, shares, (_numeric(a) or 0) >= BINDING_ACTIVE_SHARE_PCT),
        result(
            "starved_blocked",
            s,
            idle,
            (v := _numeric(s)) is not None and v <= BINDING_IDLE_SHARE_PCT,
            lowest=True,
        ),
    )
    picks = {r.method: r.resource_code or NONE for r in results}
    votes: dict[str, int] = {}
    for r in results:
        if r.resource_code:
            votes[r.resource_code] = votes.get(r.resource_code, 0) + 1
    reasons: list[Reason] = []
    internal = bool(votes) and (picks["utilisation"] != NONE or max(votes.values()) >= 2)
    if internal:
        answer = max(sorted(votes), key=lambda c: (votes[c], c == picks["utilisation"]))
        kind = "internal"
        reasons.append(
            Reason(
                "methods_agree", {"count": votes[answer], "total": len(METHODS), "machine": answer}
            )
        )
        for r in results:
            if r.resource_code != answer:
                reasons.append(
                    Reason(
                        f"method_differs_{r.method}",
                        {"machine": r.resource_code or NONE, "top": r.top_code or NONE},
                    )
                )
    else:
        answer = NONE
        material = _material(plant, *span)
        late = _numeric(material)
        if late is not None and late >= MATERIAL_SHARE_PCT:
            kind = "material"
            reasons.append(Reason("material_late", {"share_pct": late}))
        else:
            kind = "market"
            reasons.append(
                Reason(
                    "no_machine_binding", {"top": _top(busy) or NONE, "busy_pct": _numeric(u) or 0}
                )
            )
    agree = agreement(picks, answer, span)
    level = {4: Confidence.HIGH, 3: Confidence.HIGH, 2: Confidence.MEDIUM}.get(
        sum(1 for m in METHODS if picks[m] == answer), Confidence.LOW
    )
    evidence = weakest(r.evidence.confidence for r in results if not r.evidence.is_missing)
    if evidence.value < level.value:
        level = evidence
        reasons.append(Reason("weak_evidence", {"level": evidence.label}))
    for impact in gap_impacts:
        cap = Confidence.MEDIUM if impact is Confidence.HIGH else level
        if cap.value < level.value:
            level = cap
            reasons.append(Reason("data_gap"))
            break
    return Detection(
        resource_code=None if answer == NONE else answer,
        kind=kind,
        agreement=agree,
        confidence=level,
        reasons=tuple(reasons),
        methods=results,
        period_start_at=span[0],
        period_end_at=span[1],
    )


def detect_periods(
    plant: LoadedPlant,
    facts: Sequence["Fact"],
    gap_impacts: Sequence[Confidence] = (),
    kinds: Sequence[str] = ("all", "month", "week"),
) -> list[tuple[str, Detection]]:
    """Detection for every period the facts cover (whole period, months, weeks)."""
    from constraint_engine.reconstruct.durations import pair_operations
    from constraint_engine.reconstruct.states import machine_states
    from constraint_engine.reconstruct.timeline import to_min

    states = machine_states(plant, pair_operations(plant))
    grouped: dict[tuple[str, datetime], dict[str, dict[str, Figure]]] = {}
    for f in facts:
        start = f.figure.period_start_at
        if f.period_kind not in kinds or start is None:
            continue
        key = {
            ("utilisation", "utilisation_pct"): "busy",
            ("wip", "wip_average_units"): "waiting",
            ("state_share", "starved_pct"): "starved",
            ("state_share", "blocked_pct"): "blocked",
        }.get((f.family, f.measure))
        if key:
            grouped.setdefault((f.period_kind, start), {}).setdefault(key, {})[f.subject_code] = (
                f.figure
            )
    out = []
    for (kind, start), parts in sorted(
        grouped.items(), key=lambda kv: (kinds.index(kv[0][0]), kv[0][1])
    ):
        end = next(iter(parts["busy"].values())).period_end_at
        if end is None:
            continue
        window = (to_min(start), to_min(end))
        out.append(
            (
                kind,
                detect(
                    plant,
                    states,
                    window,
                    parts.get("busy", {}),
                    parts.get("waiting", {}),
                    parts.get("starved", {}),
                    parts.get("blocked", {}),
                    gap_impacts,
                ),
            )
        )
    return out
