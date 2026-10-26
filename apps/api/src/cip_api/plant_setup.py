"""Plant setup page backend (mockup F5): plant, stations, machines, operations, products,
setup families and capacity costs.

Items 1-3 of docs/input-data.md (plant, stations, machines) are entered here at kick-off; the
rest comes from imports and can be corrected here. Numbers come from the engine as Figures:
measured times from the last import's reconstruction, throughput per unit from its formula.
"""

import json
import re
from typing import Annotated, Any
from zoneinfo import available_timezones

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, TypeAdapter, ValidationError, field_validator
from sqlalchemy import text

from cip_api.auth.roles import Decision
from cip_api.auth.sessions import audit
from cip_api.corrections import record_removal
from cip_api.errors import ApiProblem
from cip_api.figures import FigureOut
from cip_api.refresh import DataChanged
from cip_api.tenancy import Ctx, require
from cip_schema.types import ResourceCode
from constraint_engine.figure import Missing
from constraint_engine.formulas.throughput import throughput_per_unit_eur_cents

router = APIRouter(tags=["plant setup"])
View = Annotated[Ctx, Depends(require(page="setup"))]
Edit = Annotated[Ctx, Depends(require(page="setup", decision=Decision.EDIT_SETUP_CALENDAR))]
CODE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{0,31}$")


STEP_CODE: TypeAdapter[str] = TypeAdapter(ResourceCode)


def _step_code(value: str) -> str:
    """The step code rule of the standard model (ADR-0009), with a plain error."""
    try:
        return STEP_CODE.validate_python(value.strip().upper())
    except ValidationError:
        raise ApiProblem("bad_step_code") from None


def _code(value: str) -> str:
    value = value.strip().upper()
    if not CODE.fullmatch(value):
        raise ValueError("use capitals, digits, - or _ (max 32)")
    return value


class PlantIn(BaseModel):
    plant_code: str
    name: str = Field(min_length=1, max_length=200)
    timezone_iana: str = "Europe/Amsterdam"

    _c = field_validator("plant_code")(_code)

    @field_validator("timezone_iana")
    @classmethod
    def _tz(cls, v: str) -> str:
        if v not in available_timezones():
            raise ValueError("unknown time zone")
        return v


class StationIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ResourceIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    station_code: str
    kind: str = Field(default="machine", pattern="^(machine|manual|station|work_centre)$")
    parallel_units: int = Field(default=1, ge=1, le=100)

    _c = field_validator("station_code")(_code)


class ChangeoverIn(BaseModel):
    resource_code: str
    from_setup_family: str = Field(min_length=1, max_length=100)
    to_setup_family: str = Field(min_length=1, max_length=100)
    changeover_min: float = Field(ge=0, le=10_000)


class CapacityCostIn(BaseModel):
    overtime_eur_cents_per_h: int | None = Field(default=None, ge=0)
    extra_shift_eur_cents: int | None = Field(default=None, ge=0)


class MachineOut(BaseModel):
    resource_code: str
    name: str
    kind: str
    parallel_units: int
    has_station_login: bool
    imported: bool = False
    """From an upload: removing it is stored as a correction, with a reason (ADR-0010)."""


class StationOut(BaseModel):
    station_code: str
    name: str
    machines: list[MachineOut]
    imported: bool = False


class OperationOut(BaseModel):
    resource_code: str
    operation: str
    erp_min_per_unit: float | None
    """ERP standard, for reference only."""
    measured_min_per_unit: FigureOut | None
    """Median measured time from the last import (formula task_time_median_v1)."""
    alternatives: list[str]
    used_by: list[str]
    """Product families whose routing uses this operation on this machine."""


class ProductOut(BaseModel):
    sku: str
    name: str
    family: str
    setup_family: str | None
    sales_price_eur_cents: int
    truly_variable_cost_eur_cents: int
    throughput_per_unit: FigureOut


class ChangeoverOut(ChangeoverIn):
    pass


class CapacityCostOut(CapacityCostIn):
    resource_code: str


class SetupOut(BaseModel):
    plant_code: str
    name: str
    timezone_iana: str
    stations: list[StationOut]
    operations: list[OperationOut]
    products: list[ProductOut]
    changeovers: list[ChangeoverOut]
    capacity_costs: list[CapacityCostOut]
    measured_from_import: str | None
    """Import the measured times come from; None until a plant has been imported."""


class _Costs:
    def __init__(self, price: int, cost: int) -> None:
        self.sales_price_eur_cents: int | Missing = price
        self.truly_variable_cost_eur_cents: int | Missing = cost


def _exists(ctx: Ctx, plant_code: str) -> None:
    ctx.check_plant(plant_code)
    found = ctx.db.execute(text("SELECT 1 FROM plants WHERE plant_code = :p"), {"p": plant_code})
    if found.first() is None:
        raise ApiProblem("plant_not_found")


@router.post("/plants", response_model=SetupOut, status_code=201)
def create_plant(body: PlantIn, ctx: Edit) -> SetupOut:
    taken = ctx.db.execute(
        text("SELECT 1 FROM plants WHERE plant_code = :p"), {"p": body.plant_code}
    ).first()
    if taken:
        raise ApiProblem("plant_exists")
    ctx.db.execute(
        text(
            "INSERT INTO plants (tenant_id, plant_code, name, timezone_iana) "
            "VALUES (:t, :p, :n, :z)"
        ),
        {
            "t": ctx.principal.tenant_id,
            "p": body.plant_code,
            "n": body.name,
            "z": body.timezone_iana,
        },
    )
    audit(ctx.db, ctx.principal.tenant_id, ctx.principal.actor, "plant_created", body.plant_code)
    return setup(body.plant_code, ctx)


@router.get("/plants/{plant_code}/setup", response_model=SetupOut)
def setup(plant_code: str, ctx: View) -> SetupOut:
    _exists(ctx, plant_code)
    p = {"p": plant_code}
    db = ctx.db
    plant = db.execute(
        text("SELECT name, timezone_iana FROM plants WHERE plant_code = :p"), p
    ).one()
    logins = set(
        db.execute(
            text("SELECT resource_code FROM station_logins WHERE plant_code = :p"), p
        ).scalars()
    )
    machines: dict[str, list[MachineOut]] = {}
    for r in db.execute(
        text(
            "SELECT resource_code, name, kind, parallel_units, station_code, "
            "import_id IS NOT NULL AS imported FROM resources "
            "WHERE plant_code = :p ORDER BY resource_code"
        ),
        p,
    ):
        machines.setdefault(r.station_code, []).append(
            MachineOut(
                resource_code=r.resource_code,
                name=r.name,
                kind=r.kind,
                parallel_units=r.parallel_units,
                has_station_login=r.resource_code in logins,
                imported=r.imported,
            )
        )
    stations = [
        StationOut(
            station_code=s.station_code,
            name=s.name,
            machines=machines.pop(s.station_code, []),
            imported=s.imported,
        )
        for s in db.execute(
            text(
                "SELECT station_code, name, import_id IS NOT NULL AS imported FROM stations "
                "WHERE plant_code = :p ORDER BY station_code"
            ),
            p,
        )
    ]
    stations += [StationOut(station_code=c, name=c, machines=m) for c, m in machines.items()]

    last = db.execute(
        text(
            "SELECT import_id, report FROM imports WHERE plant_code = :p AND status = 'done' "
            "ORDER BY created_at DESC LIMIT 1"
        ),
        p,
    ).first()
    measured = {
        (t["resource_code"], t["operation"]): FigureOut.model_validate(t["median_min_per_unit"])
        for t in (json.loads(last.report).get("task_times", []) if last else [])
    }
    steps = db.execute(
        text(
            "SELECT s.resource_code, s.operation, s.alternative_resource_codes, "
            "s.standard_run_min_per_unit, p.family FROM routing_steps s "
            "LEFT JOIN products p ON p.plant_code = s.plant_code AND p.sku = s.sku "
            "WHERE s.plant_code = :p"
        ),
        p,
    ).all()
    erp = {
        (r.resource_code, r.operation): r.standard_run_min_per_unit
        for r in db.execute(
            text(
                "SELECT resource_code, operation, standard_run_min_per_unit "
                "FROM resource_operations WHERE plant_code = :p"
            ),
            p,
        )
    }
    keys = sorted(set(erp) | {(s.resource_code, s.operation) for s in steps})
    operations = []
    for key in keys:
        uses = [s for s in steps if (s.resource_code, s.operation) == key]
        alternatives = sorted(
            {a for s in uses for a in (s.alternative_resource_codes or "").split(",") if a}
        )
        standard = erp.get(key)
        if standard is None:
            standard = next(
                (s.standard_run_min_per_unit for s in uses if s.standard_run_min_per_unit), None
            )
        operations.append(
            OperationOut(
                resource_code=key[0],
                operation=key[1],
                erp_min_per_unit=standard,
                measured_min_per_unit=measured.get(key),
                alternatives=alternatives,
                used_by=sorted({s.family for s in uses if s.family}),
            )
        )
    products = [
        ProductOut(
            sku=r.sku,
            name=r.name,
            family=r.family,
            setup_family=r.setup_family,
            sales_price_eur_cents=r.sales_price_eur_cents,
            truly_variable_cost_eur_cents=r.truly_variable_cost_eur_cents,
            throughput_per_unit=FigureOut.from_figure(
                throughput_per_unit_eur_cents(
                    _Costs(r.sales_price_eur_cents, r.truly_variable_cost_eur_cents)
                )
            ),
        )
        for r in db.execute(
            text(
                "SELECT sku, name, family, setup_family, sales_price_eur_cents, "
                "truly_variable_cost_eur_cents FROM products WHERE plant_code = :p ORDER BY sku"
            ),
            p,
        )
    ]
    changeovers = [
        ChangeoverOut.model_validate(r._mapping)
        for r in db.execute(
            text(
                "SELECT resource_code, from_setup_family, to_setup_family, changeover_min "
                "FROM changeovers WHERE plant_code = :p ORDER BY resource_code, from_setup_family, "
                "to_setup_family"
            ),
            p,
        )
    ]
    costs = [
        CapacityCostOut.model_validate(r._mapping)
        for r in db.execute(
            text(
                "SELECT resource_code, overtime_eur_cents_per_h, extra_shift_eur_cents "
                "FROM capacity_costs WHERE plant_code = :p ORDER BY resource_code"
            ),
            p,
        )
    ]
    return SetupOut(
        plant_code=plant_code,
        name=plant.name,
        timezone_iana=plant.timezone_iana,
        stations=stations,
        operations=operations,
        products=products,
        changeovers=changeovers,
        capacity_costs=costs,
        measured_from_import=str(last.import_id) if last else None,
    )


def _log(ctx: Ctx, action: str, target: str, detail: Any = "") -> None:
    audit(ctx.db, ctx.principal.tenant_id, ctx.principal.actor, action, target, str(detail))


@router.put("/plants/{plant_code}/stations/{station_code}", response_model=SetupOut)
def put_station(
    plant_code: str, station_code: str, body: StationIn, ctx: Edit, changed: DataChanged
) -> SetupOut:
    changed(ctx, plant_code, "setup")
    _exists(ctx, plant_code)
    code = _code(station_code)
    ctx.db.execute(
        text(
            "INSERT INTO stations (tenant_id, plant_code, station_code, name) "
            "VALUES (:t, :p, :s, :n) "
            "ON CONFLICT (tenant_id, plant_code, station_code) DO UPDATE SET name = EXCLUDED.name, "
            "import_id = NULL"
        ),
        {"t": ctx.principal.tenant_id, "p": plant_code, "s": code, "n": body.name},
    )
    _log(ctx, "station_saved", f"{plant_code}/{code}")
    return setup(plant_code, ctx)


@router.put("/plants/{plant_code}/resources/{resource_code}", response_model=SetupOut)
def put_resource(
    plant_code: str, resource_code: str, body: ResourceIn, ctx: Edit, changed: DataChanged
) -> SetupOut:
    changed(ctx, plant_code, "setup")
    _exists(ctx, plant_code)
    code = _step_code(resource_code)
    station = ctx.db.execute(
        text("SELECT 1 FROM stations WHERE plant_code = :p AND station_code = :s"),
        {"p": plant_code, "s": body.station_code},
    ).first()
    if station is None:
        raise ApiProblem("unknown_station")
    ctx.db.execute(
        text(
            "INSERT INTO resources (tenant_id, plant_code, resource_code, name, kind, "
            "station_code, "
            "parallel_units) VALUES (:t, :p, :r, :n, :k, :s, :u) "
            "ON CONFLICT (tenant_id, plant_code, resource_code) DO UPDATE SET "
            "name = EXCLUDED.name, "
            "kind = EXCLUDED.kind, station_code = EXCLUDED.station_code, "
            "parallel_units = EXCLUDED.parallel_units, import_id = NULL"
        ),
        {
            "t": ctx.principal.tenant_id,
            "p": plant_code,
            "r": code,
            "n": body.name,
            "k": body.kind,
            "s": body.station_code,
            "u": body.parallel_units,
        },
    )
    _log(ctx, "machine_saved", f"{plant_code}/{code}", f"station {body.station_code}")
    return setup(plant_code, ctx)


@router.delete("/plants/{plant_code}/resources/{resource_code}", response_model=SetupOut)
def delete_resource(
    plant_code: str, resource_code: str, ctx: Edit, changed: DataChanged, reason: str | None = None
) -> SetupOut:
    """Remove a step. One from an upload needs a reason and stays out of later rebuilds."""
    changed(ctx, plant_code, "setup")
    _exists(ctx, plant_code)
    login = ctx.db.execute(
        text("SELECT 1 FROM station_logins WHERE plant_code = :p AND resource_code = :r"),
        {"p": plant_code, "r": resource_code},
    ).first()
    if login:
        raise ApiProblem("machine_has_station_login")
    step = ctx.db.execute(
        text(
            "SELECT import_id IS NOT NULL AS imported FROM resources "
            "WHERE plant_code = :p AND resource_code = :r"
        ),
        {"p": plant_code, "r": resource_code},
    ).first()
    if step is None:
        raise ApiProblem("machine_not_found")
    touchpoints = ctx.db.execute(
        text("SELECT count(*) FROM operation_events WHERE plant_code = :p AND resource_code = :r"),
        {"p": plant_code, "r": resource_code},
    ).scalar_one()
    if touchpoints:
        raise ApiProblem("step_has_touchpoints", count=touchpoints)
    if step.imported:
        record_removal(ctx, plant_code, "resources", [resource_code], reason)
    ctx.db.execute(
        text("DELETE FROM resources WHERE plant_code = :p AND resource_code = :r"),
        {"p": plant_code, "r": resource_code},
    )
    _log(ctx, "machine_deleted", f"{plant_code}/{resource_code}", reason or "")
    return setup(plant_code, ctx)


@router.delete("/plants/{plant_code}/stations/{station_code}", response_model=SetupOut)
def delete_station(
    plant_code: str, station_code: str, ctx: Edit, changed: DataChanged, reason: str | None = None
) -> SetupOut:
    """Remove a station without steps. One from an upload needs a reason (ADR-0010)."""
    changed(ctx, plant_code, "setup")
    _exists(ctx, plant_code)
    station = ctx.db.execute(
        text(
            "SELECT import_id IS NOT NULL AS imported FROM stations "
            "WHERE plant_code = :p AND station_code = :s"
        ),
        {"p": plant_code, "s": station_code},
    ).first()
    if station is None:
        raise ApiProblem("station_not_found")
    used = ctx.db.execute(
        text("SELECT 1 FROM resources WHERE plant_code = :p AND station_code = :s"),
        {"p": plant_code, "s": station_code},
    ).first()
    if used:
        raise ApiProblem("station_in_use")
    if station.imported:
        record_removal(ctx, plant_code, "stations", [station_code], reason)
    ctx.db.execute(
        text("DELETE FROM stations WHERE plant_code = :p AND station_code = :s"),
        {"p": plant_code, "s": station_code},
    )
    _log(ctx, "station_deleted", f"{plant_code}/{station_code}", reason or "")
    return setup(plant_code, ctx)


@router.put("/plants/{plant_code}/changeovers", response_model=SetupOut)
def put_changeover(
    plant_code: str, body: ChangeoverIn, ctx: Edit, changed: DataChanged
) -> SetupOut:
    changed(ctx, plant_code, "setup")
    _exists(ctx, plant_code)
    ctx.db.execute(
        text(
            "INSERT INTO changeovers (tenant_id, plant_code, resource_code, from_setup_family, "
            "to_setup_family, changeover_min) VALUES (:t, :p, :r, :f, :to, :m) "
            "ON CONFLICT (tenant_id, plant_code, resource_code, from_setup_family, "
            "to_setup_family) "
            "DO UPDATE SET changeover_min = EXCLUDED.changeover_min, import_id = NULL"
        ),
        {
            "t": ctx.principal.tenant_id,
            "p": plant_code,
            "r": body.resource_code,
            "f": body.from_setup_family,
            "to": body.to_setup_family,
            "m": body.changeover_min,
        },
    )
    _log(
        ctx,
        "changeover_saved",
        f"{plant_code}/{body.resource_code}",
        f"{body.from_setup_family} -> {body.to_setup_family}: {body.changeover_min} min",
    )
    return setup(plant_code, ctx)


@router.put("/plants/{plant_code}/capacity-costs/{resource_code}", response_model=SetupOut)
def put_capacity_cost(
    plant_code: str, resource_code: str, body: CapacityCostIn, ctx: Edit, changed: DataChanged
) -> SetupOut:
    changed(ctx, plant_code, "setup")
    _exists(ctx, plant_code)
    ctx.db.execute(
        text(
            "INSERT INTO capacity_costs (tenant_id, plant_code, resource_code, "
            "overtime_eur_cents_per_h, extra_shift_eur_cents) VALUES (:t, :p, :r, :o, :x) "
            "ON CONFLICT (tenant_id, plant_code, resource_code) DO UPDATE SET "
            "overtime_eur_cents_per_h = EXCLUDED.overtime_eur_cents_per_h, "
            "extra_shift_eur_cents = EXCLUDED.extra_shift_eur_cents, import_id = NULL"
        ),
        {
            "t": ctx.principal.tenant_id,
            "p": plant_code,
            "r": resource_code,
            "o": body.overtime_eur_cents_per_h,
            "x": body.extra_shift_eur_cents,
        },
    )
    _log(ctx, "capacity_cost_saved", f"{plant_code}/{resource_code}")
    return setup(plant_code, ctx)
