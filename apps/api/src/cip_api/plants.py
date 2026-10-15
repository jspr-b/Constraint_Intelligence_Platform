"""Plant endpoints. Numbers come from the engine as Figures; the API only reads and forwards."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from cip_api.figures import FigureOut
from cip_api.tenancy import Ctx, require
from constraint_engine.summary import record_count

router = APIRouter(prefix="/plants", tags=["plants"])

COUNTED = {
    "resources": "resources",
    "products": "products",
    "orders": "orders",
    "events": "operation_events",
}


class PlantOut(BaseModel):
    plant_code: str
    name: str
    timezone_iana: str


class PlantSummaryOut(BaseModel):
    plant_code: str
    plant_name: str
    counts: dict[str, FigureOut]
    event_period_start_at: datetime | None
    event_period_end_at: datetime | None


@router.get("", response_model=list[PlantOut])
def list_plants(ctx: Annotated[Ctx, Depends(require())]) -> list[PlantOut]:
    """The plants this role may see: all, or only its own (ADR-0007)."""
    rows = ctx.db.execute(text("SELECT plant_code, name, timezone_iana FROM plants ORDER BY name"))
    return [PlantOut.model_validate(r._mapping) for r in rows if ctx.can_see_plant(r.plant_code)]


class ResourceOut(BaseModel):
    resource_code: str
    name: str
    kind: str
    station_code: str
    parallel_units: int


@router.get("/{plant_code}/resources", response_model=list[ResourceOut])
def list_resources(plant_code: str, ctx: Annotated[Ctx, Depends(require())]) -> list[ResourceOut]:
    """Machines of a plant (for pickers; the Plant setup page manages them)."""
    ctx.check_plant(plant_code)
    rows = ctx.db.execute(
        text(
            "SELECT resource_code, name, kind, station_code, parallel_units FROM resources "
            "WHERE plant_code = :p ORDER BY resource_code"
        ),
        {"p": plant_code},
    )
    return [ResourceOut.model_validate(r._mapping) for r in rows]


@router.get("/{plant_code}/summary", response_model=PlantSummaryOut)
def plant_summary(
    plant_code: str, ctx: Annotated[Ctx, Depends(require(page="data"))]
) -> PlantSummaryOut:
    ctx.check_plant(plant_code)
    db = ctx.db
    plant = db.execute(
        text("SELECT name FROM plants WHERE plant_code = :p"), {"p": plant_code}
    ).first()
    if plant is None:
        raise HTTPException(404, "plant not found")
    counts = {}
    for name, table in COUNTED.items():
        n = db.execute(
            text(f"SELECT count(*) FROM {table} WHERE plant_code = :p"), {"p": plant_code}
        ).scalar_one()
        counts[name] = FigureOut.from_figure(record_count(name, int(n), 0))
    period = db.execute(
        text("SELECT min(at), max(at) FROM operation_events WHERE plant_code = :p"),
        {"p": plant_code},
    ).one()
    return PlantSummaryOut(
        plant_code=plant_code,
        plant_name=plant[0],
        counts=counts,
        event_period_start_at=period[0],
        event_period_end_at=period[1],
    )
