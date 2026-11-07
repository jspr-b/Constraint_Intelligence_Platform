"""The plant's flow found in its touchpoints (CI0005 seq 06).

The facts job finds it from the whole plant as stored (all kept imports and fixes) after every
data change and keeps the latest per plant, so the flow is there as soon as an upload has run;
no button. The engine counts; this module stores and serves what it found.
"""

import json
import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import Connection, text

from cip_api.facts import FactRunOut, _plant, fact_run
from cip_api.figures import FigureOut
from cip_api.tenancy import Ctx, require
from constraint_engine.reconstruct.routes import PlantFlow

router = APIRouter(tags=["flow"])


class RouteOut(BaseModel):
    steps: list[str]
    jobs: int
    share: FigureOut
    """Share of all jobs counted that take this route."""
    rework: bool
    uncertain_jobs: int
    less_certain: bool


class ArrowOut(BaseModel):
    from_step: str
    to_step: str
    jobs: int
    share: FigureOut
    """Share of the jobs leaving ``from_step`` that go to ``to_step``."""
    rework: bool
    uncertain_jobs: int
    less_certain: bool


class FlowStepOut(BaseModel):
    code: str
    jobs: int
    first_jobs: int
    """Jobs whose path starts here (from Input)."""
    last_jobs: int
    """Jobs whose path ends here (to Output)."""
    missing_finish: int


class FlowOut(BaseModel):
    plant_code: str
    run: FactRunOut | None
    import_id: uuid.UUID | None
    jobs: int
    routes: list[RouteOut]
    other_routes_jobs: int
    arrows: list[ArrowOut]
    steps: list[FlowStepOut]
    overlapping_jobs: int
    period_start_at: datetime | None
    period_end_at: datetime | None
    rule: str


def flow_json(flow: PlantFlow) -> dict[str, Any]:
    return {
        "jobs": flow.jobs,
        "routes": [
            {
                "steps": list(r.steps),
                "jobs": r.jobs,
                "share": r.share.to_dict(),
                "rework": r.rework,
                "uncertain_jobs": r.uncertain_jobs,
                "less_certain": r.less_certain,
            }
            for r in flow.routes
        ],
        "other_routes_jobs": flow.other_routes_jobs,
        "arrows": [
            {
                "from_step": a.from_step,
                "to_step": a.to_step,
                "jobs": a.jobs,
                "share": a.share.to_dict(),
                "rework": a.rework,
                "uncertain_jobs": a.uncertain_jobs,
                "less_certain": a.less_certain,
            }
            for a in flow.arrows
        ],
        "steps": [
            {
                "code": s.code,
                "jobs": s.jobs,
                "first_jobs": s.first,
                "last_jobs": s.last,
                "missing_finish": s.missing_finish,
            }
            for s in flow.steps
        ],
        "overlapping_jobs": flow.overlapping_jobs,
        "period_start_at": flow.period_start_at.isoformat() if flow.period_start_at else None,
        "period_end_at": flow.period_end_at.isoformat() if flow.period_end_at else None,
        "rule": flow.rule,
    }


def store_flow(
    conn: Connection, tenant: uuid.UUID, plant_code: str, import_id: uuid.UUID, flow: PlantFlow
) -> None:
    conn.execute(
        text(
            "INSERT INTO plant_flows (tenant_id, plant_code, import_id, flow) "
            "VALUES (:t, :p, :i, :f) ON CONFLICT (tenant_id, plant_code) "
            "DO UPDATE SET import_id = excluded.import_id, flow = excluded.flow"
        ),
        {"t": tenant, "p": plant_code, "i": import_id, "f": json.dumps(flow_json(flow))},
    )


@router.get("/plants/{plant_code}/flow", response_model=FlowOut)
def read_flow(plant_code: str, ctx: Annotated[Ctx, Depends(require())]) -> FlowOut:
    """The flow found in the plant's touchpoints: routes with the share of jobs on each, arrows
    with the share of jobs leaving a step, and what is less certain. Empty until data has run."""
    _plant(ctx, plant_code)
    row = ctx.db.execute(
        text("SELECT import_id, flow FROM plant_flows WHERE plant_code = :p"), {"p": plant_code}
    ).first()
    if row is None:
        return FlowOut(
            plant_code=plant_code,
            run=None,
            import_id=None,
            jobs=0,
            routes=[],
            other_routes_jobs=0,
            arrows=[],
            steps=[],
            overlapping_jobs=0,
            period_start_at=None,
            period_end_at=None,
            rule="",
        )
    return FlowOut.model_validate(
        {
            **json.loads(row.flow),
            "plant_code": plant_code,
            "import_id": row.import_id,
            "run": fact_run(ctx.db, row.import_id),
        }
    )
