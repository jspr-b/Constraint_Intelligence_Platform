"""Measured facts: calculated once after each import, read by every page.

After an import is stored, the job ``compute_facts`` runs the engine's reconstruction
(``constraint_engine.facts.measured_facts``) on the import's standard files and replaces the
plant's facts in one transaction. ``fact_runs`` records calculating, ready or failed per import,
so the Import page and the getting-started guide can say where the numbers are.
"""

import contextlib
import json
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import Connection, text

from cip_api.auth.roles import Money
from cip_api.auth.sessions import tenant_conn
from cip_api.errors import ApiProblem
from cip_api.figures import FigureOut, MissingOut, money_out
from cip_api.jobs import enqueue
from cip_api.settings import Settings
from cip_api.tenancy import Ctx, require
from constraint_engine.facts import Fact, measured_facts
from constraint_engine.figure import Figure, Missing
from constraint_engine.formulas.money import NO_RATE
from constraint_engine.formulas.registry import registry
from constraint_engine.io.plant_loader import load_plant
from constraint_engine.loss import loss_facts

FactStatus = Literal["calculating", "ready", "failed"]


class FactRunOut(BaseModel):
    """Where the plant's numbers are after an import."""

    status: FactStatus
    started_at: datetime
    finished_at: datetime | None
    period_start_at: datetime | None
    period_end_at: datetime | None
    error: str | None
    """Technical cause when failed (for IT); the page shows a plain message instead."""


def fact_run(conn: Connection, import_id: uuid.UUID) -> FactRunOut | None:
    row = conn.execute(
        text(
            "SELECT status, started_at, finished_at, period_start_at, period_end_at, error "
            "FROM fact_runs WHERE import_id = :i"
        ),
        {"i": import_id},
    ).first()
    return FactRunOut.model_validate(dict(row._mapping)) if row else None


def start_facts(conn: Connection, tenant: uuid.UUID, plant_code: str, import_id: uuid.UUID) -> None:
    """Mark the import's numbers as calculating (in the caller's transaction)."""
    conn.execute(
        text(
            "INSERT INTO fact_runs (tenant_id, import_id, plant_code) VALUES (:t, :i, :p) "
            "ON CONFLICT (tenant_id, import_id) DO UPDATE SET status = 'calculating', "
            "started_at = now(), finished_at = NULL, error = NULL"
        ),
        {"t": tenant, "i": import_id, "p": plant_code},
    )


def queue_facts(settings: Settings, tenant: uuid.UUID, import_id: uuid.UUID) -> None:
    """Run the calculation now (inline jobs, tests) or in a worker."""
    if settings.run_jobs_inline:
        with contextlib.suppress(Exception):  # the failure is recorded on the fact run
            compute_facts(settings, tenant, import_id)
    else:
        enqueue("compute_facts", str(tenant), str(import_id))


def _version(formula_id: str) -> int:
    return registry.get(formula_id).version


def fact_row(tenant: uuid.UUID, plant_code: str, import_id: uuid.UUID, f: Fact) -> dict[str, Any]:
    fig = f.figure.to_dict()
    missing = f.figure.value if isinstance(f.figure.value, Missing) else None
    return {
        "t": tenant,
        "p": plant_code,
        "i": import_id,
        "family": f.family,
        "subject": f.subject_code,
        "measure": f.measure,
        "operation": f.operation,
        "reason": f.reason_code,
        "kind": f.period_kind,
        "start": f.figure.period_start_at,
        "end": f.figure.period_end_at,
        "value": None if missing else float(f.figure.value),  # type: ignore[arg-type]
        "unit": f.figure.unit,
        "formula": f.figure.formula_id,
        "version": _version(f.figure.formula_id),
        "confidence": f.figure.confidence.label,
        "inputs": json.dumps(fig["inputs"], ensure_ascii=False, default=str),
        "missing": json.dumps(missing.to_dict()) if missing else None,
    }


INSERT = text(
    "INSERT INTO facts (tenant_id, plant_code, import_id, family, subject_code, measure, "
    "operation, reason_code, period_kind, period_start_at, period_end_at, value, unit, formula_id, "
    "formula_version, confidence, inputs, missing) VALUES (:t, :p, :i, :family, :subject, "
    ":measure, :operation, :reason, :kind, :start, :end, :value, :unit, :formula, :version, "
    ":confidence, :inputs, :missing)"
)


class NoEventsError(RuntimeError):
    """The import has no touchpoints to calculate from."""


def compute_facts(settings: Settings, tenant: uuid.UUID, import_id: uuid.UUID) -> int:
    """The job: reconstruct the import's data and replace the plant's facts. Returns the count."""
    from cip_api.detection import detect, store_detections  # detection.py reads this module
    from cip_api.imports import import_dir  # imports.py queues this job

    try:
        with tenant_conn(settings, tenant) as conn:
            plant_code, report = conn.execute(
                text("SELECT plant_code, report FROM imports WHERE import_id = :i"),
                {"i": import_id},
            ).one()
        plant = load_plant(import_dir(settings, tenant, plant_code, import_id) / "standard")
        if not plant.events:
            # Nothing to calculate from: fail, so the plant's previous numbers stay.
            raise NoEventsError("the import's standard layout has no events")
        facts = measured_facts(plant)
        detections = detect(plant, facts, report)
        facts += loss_facts(plant, facts, detections)
        whole = next((f.figure for f in facts if f.period_kind == "all"), None)
        rows = [fact_row(tenant, plant_code, import_id, f) for f in facts]
        with tenant_conn(settings, tenant) as conn:
            conn.execute(text("DELETE FROM facts WHERE plant_code = :p"), {"p": plant_code})
            if rows:
                conn.execute(INSERT, rows)
            store_detections(conn, tenant, plant_code, import_id, detections)
            conn.execute(
                text(
                    "UPDATE fact_runs SET status = 'ready', finished_at = :now, error = NULL, "
                    "period_start_at = :s, period_end_at = :e WHERE import_id = :i"
                ),
                {
                    "now": datetime.now(UTC),
                    "s": whole.period_start_at if whole else None,
                    "e": whole.period_end_at if whole else None,
                    "i": import_id,
                },
            )
        return len(rows)
    except Exception as exc:  # recorded for the page; plant values never appear here
        with tenant_conn(settings, tenant) as conn:
            conn.execute(
                text(
                    "UPDATE fact_runs SET status = 'failed', finished_at = :now, error = :e "
                    "WHERE import_id = :i"
                ),
                {"now": datetime.now(UTC), "e": f"facts:{type(exc).__name__}", "i": import_id},
            )
        raise


# --- Read API: every page reads the same stored facts ------------------------------------

router = APIRouter(tags=["facts"])
Family = Literal[
    "state",
    "state_share",
    "down_reason",
    "utilisation",
    "setup_share",
    "oee",
    "effective_capacity",
    "queue",
    "wip",
    "task_time",
    "scan_gap",
    "loss",
    "throughput",
]
PeriodKind = Literal["all", "month", "week", "day"]


class FactOut(BaseModel):
    family: Family
    resource_code: str
    measure: str
    """The number's name with its unit, e.g. ``running_min`` or ``utilisation_pct``."""
    operation: str | None
    """For task times: the operation measured on the machine."""
    reason_code: str | None = None
    """For down reasons: the plant's own down reason code (``unknown`` when none was given)."""
    period_kind: PeriodKind
    figure: FigureOut


class PeriodOut(BaseModel):
    period_kind: PeriodKind
    period_start_at: datetime
    period_end_at: datetime


class FactsOut(BaseModel):
    plant_code: str
    run: FactRunOut | None
    """The calculation the facts come from (latest import of the plant); None before any."""
    import_id: uuid.UUID | None
    facts: list[FactOut]


def _as_hours(fig: FigureOut) -> FigureOut:
    """A stored € Figure as constraint hours, converted by the engine with its own rate."""
    amount = Figure.from_dict(fig.model_dump(mode="json"))
    rate = amount.inputs.get("throughput_per_constraint_h_eur_cents")
    return money_out(amount, Money.HOURS.value, rate if isinstance(rate, Figure) else NO_RATE)


def _figure(row: Any) -> FigureOut:
    value: float | int | MissingOut
    if row.missing:
        value = MissingOut.model_validate(json.loads(row.missing))
    else:
        whole = row.measure == "wip_max_units" or row.unit == "eur_cents"  # counts and cents
        value = int(row.value) if whole else row.value
    return FigureOut(
        value=value,
        unit=row.unit,
        formula_id=row.formula_id,
        inputs=json.loads(row.inputs),
        period_start_at=row.period_start_at,
        period_end_at=row.period_end_at,
        confidence=row.confidence,
    )


def _plant(ctx: Ctx, plant_code: str) -> None:
    ctx.check_plant(plant_code)
    found = ctx.db.execute(
        text("SELECT 1 FROM plants WHERE plant_code = :p"), {"p": plant_code}
    ).first()
    if found is None:
        raise ApiProblem("plant_not_found")


@router.get("/plants/{plant_code}/facts", response_model=FactsOut)
def read_facts(
    plant_code: str,
    ctx: Annotated[Ctx, Depends(require())],
    family: Annotated[list[Family] | None, Query()] = None,
    resource_code: str | None = None,
    period_kind: PeriodKind = "all",
    period_start_at: datetime | None = None,
) -> FactsOut:
    """Measured facts of the plant's latest calculation, each a Figure with its provenance.

    Filter by ``family`` (repeatable), ``resource_code`` and period: ``period_kind`` ``all``
    (the whole data period, default), ``month`` or ``week``; ``period_start_at`` picks one month
    or week (see ``/facts/periods``), otherwise every period of that kind is returned.
    """
    _plant(ctx, plant_code)
    run = ctx.db.execute(
        text(
            "SELECT f.import_id FROM fact_runs f JOIN imports i ON i.import_id = f.import_id "
            "WHERE f.plant_code = :p ORDER BY i.created_at DESC LIMIT 1"
        ),
        {"p": plant_code},
    ).first()
    where = ["plant_code = :p", "period_kind = :k"]
    params: dict[str, Any] = {"p": plant_code, "k": period_kind}
    if family:
        where.append("family = ANY(:f)")
        params["f"] = list(family)
    if resource_code:
        where.append("subject_code = :r")
        params["r"] = resource_code
    if period_start_at:
        where.append("period_start_at = :s")
        params["s"] = period_start_at
    rows = ctx.db.execute(
        text(
            "SELECT import_id, family, subject_code, measure, operation, reason_code, period_kind, "
            "period_start_at, period_end_at, value, unit, formula_id, confidence, inputs, missing "
            f"FROM facts WHERE {' AND '.join(where)} "
            "ORDER BY subject_code, family, measure, operation, period_start_at"
        ),
        params,
    ).all()
    hours = ctx.access.money is Money.HOURS
    return FactsOut(
        plant_code=plant_code,
        run=fact_run(ctx.db, run.import_id) if run else None,
        import_id=rows[0].import_id if rows else None,
        facts=[
            FactOut(
                family=r.family,
                resource_code=r.subject_code,
                measure=r.measure,
                operation=r.operation,
                reason_code=r.reason_code,
                period_kind=r.period_kind,
                figure=_as_hours(_figure(r)) if hours and r.unit == "eur_cents" else _figure(r),
            )
            for r in rows
            # A role that sees hours only never gets a € rate either (ADR-0007).
            if not (hours and r.family == "throughput")
        ],
    )


@router.get("/plants/{plant_code}/facts/periods", response_model=list[PeriodOut])
def read_periods(plant_code: str, ctx: Annotated[Ctx, Depends(require())]) -> list[PeriodOut]:
    """The periods the plant's facts cover: the whole data period, each month and each week."""
    _plant(ctx, plant_code)
    rows = ctx.db.execute(
        text(
            "SELECT DISTINCT period_kind, period_start_at, period_end_at FROM facts "
            "WHERE plant_code = :p AND period_start_at IS NOT NULL "
            "ORDER BY period_kind, period_start_at"
        ),
        {"p": plant_code},
    ).all()
    return [PeriodOut.model_validate(dict(r._mapping)) for r in rows]
