"""Build the data quality report from a loaded plant (pure; no I/O).

Gaps never change data: they describe what is missing and how much it lowers confidence.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime

from cip_schema.transactional import EventType, OperationEvent
from constraint_engine.figure import Confidence, Figure, Missing
from constraint_engine.formulas.registry import Calc, Resolved, formula
from constraint_engine.io.plant_loader import REQUIRED, LoadedPlant, RowError

IMPACT_PENALTY = {Confidence.HIGH: 15, Confidence.MEDIUM: 7, Confidence.LOW: 2, Confidence.NONE: 0}
REJECTED_PENALTY_PER_PCT = 2
REJECTED_PENALTY_CAP = 30
FILE_IMPACT = {
    "events.csv": Confidence.HIGH,
    "orders.csv": Confidence.HIGH,
    "routings.csv": Confidence.HIGH,
    "products.csv": Confidence.HIGH,
    "resources.csv": Confidence.HIGH,
    "stations.csv": Confidence.MEDIUM,
    "calendar.csv": Confidence.MEDIUM,
    "plant.json": Confidence.MEDIUM,
}


@dataclass(frozen=True, slots=True)
class Gap:
    code: str
    description: str
    confidence_impact: Confidence
    fix: str
    resource_code: str | None = None
    count: int = 0


@dataclass(frozen=True, slots=True)
class FileQuality:
    file: str
    rows: int
    rejected: int
    reasons: dict[str, int]
    examples: tuple[RowError, ...]


@dataclass
class QualityReport:
    files: list[FileQuality]
    gaps: list[Gap]
    score: Figure
    rejected_rows: list[RowError] = field(default_factory=list)


@formula(
    "data_quality_score",
    1,
    "score = 100 − min(2 × rejected row %, 30) − Σ gap penalty (high 15, medium 7, low 2), floor 0",
    unit="score",
)
def data_quality_score(rows: int, rejected: int, gaps: list[Gap]) -> Calc:
    penalties = Counter(g.confidence_impact.label for g in gaps)

    def compute(i: Resolved) -> int:
        total = int(i["rows"]) + int(i["rejected_rows"])
        rejected_pct = 100 * int(i["rejected_rows"]) / total if total else 0.0
        penalty = min(REJECTED_PENALTY_PER_PCT * rejected_pct, REJECTED_PENALTY_CAP)
        penalty += sum(IMPACT_PENALTY[c] * int(i[f"gaps_{c.label}"]) for c in IMPACT_PENALTY)
        return max(0, round(100 - penalty))

    return Calc(
        inputs={
            "rows": rows,
            "rejected_rows": rejected,
            **{f"gaps_{c.label}": penalties.get(c.label, 0) for c in IMPACT_PENALTY},
        },
        compute=compute,
    )


def _reason_kind(reason: str) -> str:
    return reason.split(":")[0] if ":" in reason else reason.split(" ")[0]


def _files(plant: LoadedPlant, errors: list[RowError]) -> list[FileQuality]:
    counts = {
        "resources.csv": len(plant.resources),
        "products.csv": len(plant.products),
        "routings.csv": sum(len(r.steps) for r in plant.routings),
        "orders.csv": len(plant.orders),
        "events.csv": len(plant.events),
        "calendar.csv": len(plant.calendar),
        "stations.csv": len(plant.stations),
    }
    by_file: dict[str, list[RowError]] = defaultdict(list)
    for e in errors:
        by_file[e.file].append(e)
    files = set(counts) | set(by_file)
    return [
        FileQuality(
            file=f,
            rows=counts.get(f, 0),
            rejected=len(by_file[f]),
            reasons=dict(Counter(_reason_kind(e.reason) for e in by_file[f]).most_common()),
            examples=tuple(by_file[f][:5]),
        )
        for f in sorted(files)
    ]


def _unpaired(events: list[OperationEvent]) -> dict[str, int]:
    """Starts without an end per machine, ignoring the job still running at the end of the data."""
    open_jobs: dict[tuple[str, str | None, int | None], int] = Counter()
    last_start: dict[str, tuple[str | None, int | None]] = {}
    for e in sorted(events, key=lambda e: e.at):
        if e.resource_code is None:
            continue
        key = (e.resource_code, e.order_id, e.operation_seq)
        if e.event_type is EventType.START:
            open_jobs[key] += 1
            last_start[e.resource_code] = (e.order_id, e.operation_seq)
        elif e.event_type is EventType.END and open_jobs[key] > 0:
            open_jobs[key] -= 1
    out: Counter[str] = Counter()
    for (code, order, seq), n in open_jobs.items():
        running_at_end = last_start.get(code) == (order, seq)
        out[code] += n - (1 if running_at_end else 0)
    return {code: n for code, n in out.items() if n > 0}


def _event_gaps(plant: LoadedPlant) -> list[Gap]:
    gaps: list[Gap] = []
    codes = [r.resource_code for r in plant.resources]
    for code, n in sorted(_unpaired(plant.events).items()):
        gaps.append(
            Gap(
                "unpaired_start",
                f"{n} start events on {code} have no end event",
                Confidence.MEDIUM,
                "Check that the MES export includes finish bookings",
                code,
                n,
            )
        )
    downs = {
        e.resource_code
        for e in plant.events
        if e.event_type is EventType.DOWN_START and e.down_reason_code != "PM"
    }
    for code in codes:
        if code not in downs:
            gaps.append(
                Gap(
                    "no_downtime",
                    f"No breakdowns recorded for {code}",
                    Confidence.LOW,
                    "Confirm the machine had no stops, or add the maintenance log",
                    code,
                )
            )
    if plant.events and not any(e.event_type is EventType.SCRAP for e in plant.events):
        gaps.append(
            Gap(
                "no_scrap",
                "No scrap recorded anywhere: scrap figures are a lower bound",
                Confidence.MEDIUM,
                "Export scrap bookings with the operation where scrap was found",
            )
        )
    working: dict[str, set[date]] = defaultdict(set)
    for w in plant.calendar:
        if w.kind.value == "shift":
            working[w.resource_code].add(w.start_at.date())
    seen: dict[str | None, set[date]] = defaultdict(set)
    last = max((e.at.date() for e in plant.events), default=None)
    for e in plant.events:
        seen[e.resource_code].add(e.at.date())
    for code in codes:
        silent = {d for d in working[code] if last is not None and d <= last} - seen[code]
        if silent:
            gaps.append(
                Gap(
                    "silent_days",
                    f"{code} has no events on {len(silent)} working days",
                    Confidence.LOW,
                    "Check whether the machine was idle or the export missed those days",
                    code,
                    len(silent),
                )
            )
    return gaps


def quality_report(
    plant: LoadedPlant, import_errors: list[RowError] | None = None
) -> QualityReport:
    """Files, gaps and the score (0 to 100); ``import_errors`` are rows rejected before loading."""
    errors = list(import_errors or []) + plant.row_errors
    gaps = [
        Gap(
            "missing_file",
            f"{name} is missing",
            FILE_IMPACT.get(name, Confidence.LOW),
            f"Provide {name}",
        )
        for name in sorted(plant.missing_files)
        if name in REQUIRED
    ]
    gaps += _event_gaps(plant)
    files = _files(plant, errors)
    rows = sum(f.rows for f in files)
    return QualityReport(
        files=files,
        gaps=gaps,
        score=data_quality_score(rows, len(errors), gaps),
        rejected_rows=errors,
    )


@formula(
    "event_period_weeks",
    1,
    "event period = (last event − first event) in weeks, one decimal",
    unit="weeks",
)
def event_period_weeks(events: list[OperationEvent]) -> Calc:
    """How much history the events cover; Missing when there are no events."""
    times = [e.at for e in events]
    first: datetime | Missing = min(times) if times else Missing("events", "no events loaded")
    last: datetime | Missing = max(times) if times else Missing("events", "no events loaded")

    def compute(i: Resolved) -> float:
        start = datetime.fromisoformat(str(i["first_event_at"]))
        end = datetime.fromisoformat(str(i["last_event_at"]))
        return round((end - start).total_seconds() / (7 * 86_400), 1)

    return Calc(
        inputs={
            "first_event_at": first.isoformat() if isinstance(first, datetime) else first,
            "last_event_at": last.isoformat() if isinstance(last, datetime) else last,
        },
        compute=compute,
        period_start_at=first if isinstance(first, datetime) else None,
        period_end_at=last if isinstance(last, datetime) else None,
    )
