"""Data quality page backend (mockup D2): the engine's quality report of the latest import.

The report is computed by the engine when the import runs and stored with it; this endpoint
only forwards it. Missing data is listed as a gap with its confidence impact, never filled in.
"""

import json
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text

from cip_api.ai import AiExplanationsOut
from cip_api.corrections import _example
from cip_api.figures import FigureOut
from cip_api.imports import choose_mapping, import_dir
from cip_api.settings import Settings, get_settings
from cip_api.tenancy import Ctx, require

router = APIRouter(tags=["data quality"])


class FileOut(BaseModel):
    file: str
    rows: int
    rejected: int
    """Rows the import could not read and that are not fixed or left out in the app."""
    fixed: int = 0
    """Rows of the file fixed or left out in the app (ADR-0010); counted in rows, not rejected."""
    reasons: dict[str, int]
    """Rejected rows per rule: the rule's code (e.g. not_a_datetime), else its first words."""
    examples: list[dict[str, int | str]]


class GapOut(BaseModel):
    code: str
    description: str
    confidence_impact: str
    fix: str
    resource_code: str | None
    count: int


class DataQualityOut(BaseModel):
    plant_code: str
    import_id: uuid.UUID | None
    imported_at: datetime | None
    score: FigureOut | None
    rows: FigureOut | None
    files: list[FileOut]
    files_required: int
    files_missing: list[str]
    gaps: list[GapOut]
    event_period_weeks: FigureOut | None
    event_period_start_at: datetime | None
    event_period_end_at: datetime | None
    datetime_format: str | None = None
    """How the export writes a date and time, e.g. ``20-07-2026 10:11``, for the reasons."""
    ai_explanations: AiExplanationsOut | None = None
    """The AI's explanations of the rejected rows, when IT asked for them on the Import page."""


@router.get("/plants/{plant_code}/data-quality", response_model=DataQualityOut)
def data_quality(
    plant_code: str,
    ctx: Annotated[Ctx, Depends(require(page="data"))],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DataQualityOut:
    ctx.check_plant(plant_code)
    row = ctx.db.execute(
        text(
            "SELECT import_id, created_at, report FROM imports "
            "WHERE plant_code = :p AND status = 'done' ORDER BY created_at DESC LIMIT 1"
        ),
        {"p": plant_code},
    ).first()
    report = json.loads(row.report) if row and row.report else {}
    quality = report.get("quality")
    if row is None or quality is None:
        return DataQualityOut(
            plant_code=plant_code,
            import_id=None,
            imported_at=None,
            score=None,
            rows=None,
            files=[],
            files_required=0,
            files_missing=[],
            gaps=[],
            event_period_weeks=None,
            event_period_start_at=None,
            event_period_end_at=None,
        )
    return DataQualityOut(
        plant_code=plant_code,
        import_id=row.import_id,
        imported_at=row.created_at,
        datetime_format=_datetime_example(settings, ctx, plant_code, row.import_id),
        ai_explanations=report.get("ai_explanations"),
        **quality,
    )


def _datetime_example(
    settings: Settings, ctx: Ctx, plant_code: str, import_id: uuid.UUID
) -> str | None:
    folder = import_dir(settings, ctx.principal.tenant_id, plant_code, import_id) / "source"
    if not folder.exists():
        return None
    return _example(choose_mapping(p.name for p in folder.iterdir()))
