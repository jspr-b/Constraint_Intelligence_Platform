"""Constraint detection: stored per import and period by the facts job, read by every page.

The engine (``constraint_engine.detection``) runs four methods and combines them; this module
only saves its output and returns it as envelopes. Reasons are codes with values: the web app
holds the plain words.
"""

import json
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import Connection, text

from cip_api.facts import FactRunOut, _plant, fact_run
from cip_api.figures import FigureOut
from cip_api.tenancy import Ctx, require
from constraint_engine.detection import Detection, detect_periods
from constraint_engine.facts import Fact
from constraint_engine.figure import Confidence
from constraint_engine.io.plant_loader import LoadedPlant

router = APIRouter(tags=["detection"])
PeriodKind = Literal["all", "month", "week"]
IMPACT = {c.label: c for c in Confidence}


class ReasonOut(BaseModel):
    code: str
    """Message code, e.g. ``methods_agree``, ``no_machine_binding``, ``data_gap``."""
    values: dict[str, str | int | float]


class MethodOut(BaseModel):
    method: Literal["utilisation", "queue", "active_period", "starved_blocked"]
    resource_code: str | None
    """The machine this method points at; None when it finds no binding machine."""
    top_code: str | None
    """The top machine by this method, binding or not."""
    evidence: FigureOut


class DetectionOut(BaseModel):
    period_kind: PeriodKind
    period_start_at: datetime
    period_end_at: datetime
    resource_code: str | None
    """The constraint; None when no machine limits output."""
    kind: Literal["internal", "market", "material"]
    confidence: Literal["high", "medium", "low", "none"]
    agreement: FigureOut
    reasons: list[ReasonOut]
    methods: list[MethodOut]


class DetectionsOut(BaseModel):
    plant_code: str
    run: FactRunOut | None
    import_id: uuid.UUID | None
    detections: list[DetectionOut]


def gap_impacts(report: str | None) -> list[Confidence]:
    """Confidence impacts of the import's data gaps (from its quality report)."""
    gaps = (json.loads(report) if report else {}).get("quality", {}).get("gaps", [])
    return [IMPACT[g["confidence_impact"]] for g in gaps if g.get("confidence_impact") in IMPACT]


def _row(
    tenant: uuid.UUID, plant_code: str, import_id: uuid.UUID, kind: str, d: Detection
) -> dict[str, Any]:
    return {
        "t": tenant,
        "p": plant_code,
        "i": import_id,
        "kind_p": kind,
        "s": d.period_start_at,
        "e": d.period_end_at,
        "r": d.resource_code,
        "k": d.kind,
        "c": d.confidence.label,
        "a": json.dumps(d.agreement.to_dict(), default=str),
        "reasons": json.dumps([{"code": r.code, "values": dict(r.values)} for r in d.reasons]),
        "methods": json.dumps(
            [
                {
                    "method": m.method,
                    "resource_code": m.resource_code,
                    "top_code": m.top_code,
                    "evidence": m.evidence.to_dict(),
                }
                for m in d.methods
            ],
            default=str,
        ),
    }


def detect(
    plant: LoadedPlant, facts: list[Fact], report: str | None
) -> list[tuple[str, Detection]]:
    """The engine's detection for every period, with the import's data gaps."""
    return detect_periods(plant, facts, gap_impacts(report))


def store_detections(
    conn: Connection,
    tenant: uuid.UUID,
    plant_code: str,
    import_id: uuid.UUID,
    detections: list[tuple[str, Detection]],
) -> int:
    """Replace the plant's detections (in the caller's transaction). Returns the count."""
    rows = [_row(tenant, plant_code, import_id, kind, d) for kind, d in detections]
    conn.execute(text("DELETE FROM detections WHERE plant_code = :p"), {"p": plant_code})
    if rows:
        conn.execute(
            text(
                "INSERT INTO detections (tenant_id, plant_code, import_id, period_kind, "
                "period_start_at, period_end_at, resource_code, kind, confidence, agreement, "
                "reasons, methods) VALUES (:t, :p, :i, :kind_p, :s, :e, :r, :k, :c, :a, "
                ":reasons, :methods)"
            ),
            rows,
        )
    return len(rows)


@router.get("/plants/{plant_code}/detection", response_model=DetectionsOut)
def read_detection(
    plant_code: str,
    ctx: Annotated[Ctx, Depends(require())],
    period_kind: PeriodKind = "all",
    period_start_at: datetime | None = None,
) -> DetectionsOut:
    """The constraint per period from the plant's latest calculation, with every method."""
    _plant(ctx, plant_code)
    latest = ctx.db.execute(
        text(
            "SELECT f.import_id FROM fact_runs f JOIN imports i ON i.import_id = f.import_id "
            "WHERE f.plant_code = :p ORDER BY i.created_at DESC LIMIT 1"
        ),
        {"p": plant_code},
    ).first()
    where = "plant_code = :p AND period_kind = :k"
    params: dict[str, Any] = {"p": plant_code, "k": period_kind}
    if period_start_at:
        where += " AND period_start_at = :s"
        params["s"] = period_start_at
    rows = ctx.db.execute(
        text(
            "SELECT import_id, period_kind, period_start_at, period_end_at, resource_code, kind, "
            f"confidence, agreement, reasons, methods FROM detections WHERE {where} "
            "ORDER BY period_start_at"
        ),
        params,
    ).all()
    return DetectionsOut(
        plant_code=plant_code,
        run=fact_run(ctx.db, latest.import_id) if latest else None,
        import_id=rows[0].import_id if rows else None,
        detections=[
            DetectionOut(
                period_kind=r.period_kind,
                period_start_at=r.period_start_at,
                period_end_at=r.period_end_at,
                resource_code=r.resource_code,
                kind=r.kind,
                confidence=r.confidence,
                agreement=FigureOut.model_validate(json.loads(r.agreement)),
                reasons=[ReasonOut.model_validate(x) for x in json.loads(r.reasons)],
                methods=[MethodOut.model_validate(x) for x in json.loads(r.methods)],
            )
            for r in rows
        ],
    )
