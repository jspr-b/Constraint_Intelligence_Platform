"""Plant endpoints. Numbers come from the engine as Figures; the API only reads and forwards."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text

from cip_api.errors import ApiProblem
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
    positions_max: int
    """Most staffed positions in any shift (a count, never who); ``parallel_units`` when the
    shift sheet gives no positions (ADR-0009)."""


@router.get("/{plant_code}/resources", response_model=list[ResourceOut])
def list_resources(plant_code: str, ctx: Annotated[Ctx, Depends(require())]) -> list[ResourceOut]:
    """Steps of a plant, with their kind and positions (for pickers and labels; the Plant setup
    page manages them)."""
    ctx.check_plant(plant_code)
    rows = ctx.db.execute(
        text(
            "SELECT r.resource_code, r.name, r.kind, r.station_code, r.parallel_units, "
            "COALESCE((SELECT max(c.positions) FROM calendar_windows c "
            "WHERE c.plant_code = r.plant_code AND c.resource_code = r.resource_code "
            "AND c.kind = 'shift'), r.parallel_units) AS positions_max "
            "FROM resources r WHERE r.plant_code = :p ORDER BY r.resource_code"
        ),
        {"p": plant_code},
    )
    return [ResourceOut.model_validate(r._mapping) for r in rows]


class TeamOut(BaseModel):
    team_code: str
    name: str
    resource_codes: list[str]
    """The steps the team covers."""
    size_max: int | None
    """Largest team size in any shift (a count, never who); None when no sizes were sent."""


@router.get("/{plant_code}/teams", response_model=list[TeamOut])
def list_teams(plant_code: str, ctx: Annotated[Ctx, Depends(require())]) -> list[TeamOut]:
    """Teams shared by several steps (ADR-0009): code, name and steps; never who is in them."""
    ctx.check_plant(plant_code)
    rows = ctx.db.execute(
        text(
            "SELECT t.team_code, t.name, t.resource_codes, (SELECT max(s.positions) "
            "FROM team_shifts s WHERE s.plant_code = t.plant_code AND s.team_code = t.team_code) "
            "AS size_max FROM teams t WHERE t.plant_code = :p ORDER BY t.team_code"
        ),
        {"p": plant_code},
    )
    return [
        TeamOut(
            team_code=r.team_code,
            name=r.name,
            resource_codes=r.resource_codes.split(","),
            size_max=r.size_max,
        )
        for r in rows
    ]


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
        raise ApiProblem("plant_not_found")
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
