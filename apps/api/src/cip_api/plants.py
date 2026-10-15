"""Plant endpoints. Numbers come from the engine as Figures; the API only reads and forwards."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import Connection, text

from cip_api.figures import FigureOut
from cip_api.tenancy import tenant_db
from constraint_engine.summary import record_count

router = APIRouter(prefix="/plants", tags=["plants"])

COUNTED = {
    "resources": "resources",
    "products": "products",
    "orders": "orders",
    "events": "operation_events",
}


class PlantSummaryOut(BaseModel):
    plant_code: str
    plant_name: str
    counts: dict[str, FigureOut]
    event_period_start_at: datetime | None
    event_period_end_at: datetime | None


@router.get("/{plant_code}/summary", response_model=PlantSummaryOut)
def plant_summary(
    plant_code: str, db: Annotated[Connection, Depends(tenant_db)]
) -> PlantSummaryOut:
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
