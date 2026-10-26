"""Capacity calendar page backend (mockup F6): day timeline per machine, exceptions, edits.

Times are stored in UTC and shown in plant local time. ``start_min``/``end_min`` place a window
on the local day (0-1440) for drawing; they are layout positions, not capacity figures.
"""

from datetime import date, datetime, time, timedelta
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text

from cip_api.auth.roles import Decision
from cip_api.auth.sessions import audit
from cip_api.corrections import record_removal
from cip_api.db.plant_store import key_text
from cip_api.errors import ApiProblem
from cip_api.refresh import DataChanged
from cip_api.tenancy import Ctx, require

router = APIRouter(tags=["capacity calendar"])
View = Annotated[Ctx, Depends(require(page="calendar"))]
Edit = Annotated[Ctx, Depends(require(page="calendar", decision=Decision.EDIT_SETUP_CALENDAR))]
Kind = Literal["shift", "break", "maintenance", "holiday", "overtime"]
EXCEPTION_KINDS = ("maintenance", "holiday", "overtime")


class WindowOut(BaseModel):
    id: int
    resource_code: str
    kind: str
    start_at: datetime
    end_at: datetime
    covered: bool
    start_min: int
    end_min: int
    imported: bool = False
    """From an upload: removing it needs a reason and is stored as a correction (ADR-0010)."""


class MachineDay(BaseModel):
    resource_code: str
    name: str
    windows: list[WindowOut]


class OvertimeOut(BaseModel):
    resource_code: str
    iso_year: int
    iso_week: int
    overtime_h: float


class CalendarOut(BaseModel):
    plant_code: str
    timezone_iana: str
    day: date
    machines: list[MachineDay]
    exceptions: list[WindowOut]
    """Maintenance, holidays and overtime in the 12 weeks from ``day``."""
    data_start_at: datetime | None
    data_end_at: datetime | None
    overtime: list[OvertimeOut]


class WindowIn(BaseModel):
    """Times with a zone are taken as given; times without one are plant local time."""

    resource_code: str
    kind: Kind
    start_at: datetime
    end_at: datetime
    covered: bool = False

    def in_zone(self, zone: ZoneInfo) -> "WindowIn":
        def aware(at: datetime) -> datetime:
            return at if at.tzinfo else at.replace(tzinfo=zone)

        return self.model_copy(
            update={"start_at": aware(self.start_at), "end_at": aware(self.end_at)}
        )

    @model_validator(mode="after")
    def _order(self) -> "WindowIn":
        if (self.start_at.tzinfo is None) != (self.end_at.tzinfo is None):
            raise ValueError("give both times with a zone, or both as plant local time")
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        if self.end_at - self.start_at > timedelta(days=31):
            raise ValueError("a window is at most 31 days")
        if self.covered and self.kind != "break":
            raise ValueError("only breaks can be covered")
        return self


class CoveredIn(BaseModel):
    covered: bool


class OvertimeIn(BaseModel):
    resource_code: str
    iso_year: int = Field(ge=2000, le=2100)
    iso_week: int = Field(ge=1, le=53)
    overtime_h: float = Field(ge=0, le=168)


def _plant(ctx: Ctx, plant_code: str) -> str:
    ctx.check_plant(plant_code)
    tz = ctx.db.execute(
        text("SELECT timezone_iana FROM plants WHERE plant_code = :p"), {"p": plant_code}
    ).scalar_one_or_none()
    if tz is None:
        raise ApiProblem("plant_not_found")
    return str(tz)


def _window(row: object, day_start: datetime) -> WindowOut:
    def offset(at: datetime) -> int:
        return max(0, min(1440, int((at - day_start).total_seconds() // 60)))

    r = row._mapping  # type: ignore[attr-defined]
    return WindowOut(
        id=r["id"],
        resource_code=r["resource_code"],
        kind=r["kind"],
        start_at=r["start_at"],
        end_at=r["end_at"],
        covered=r["covered"],
        start_min=offset(r["start_at"]),
        end_min=offset(r["end_at"]),
        imported=r["imported"],
    )


@router.get("/plants/{plant_code}/calendar", response_model=CalendarOut)
def calendar(plant_code: str, ctx: View, day: date | None = None) -> CalendarOut:
    tz = _plant(ctx, plant_code)
    zone = ZoneInfo(tz)
    p = {"p": plant_code}
    bounds = ctx.db.execute(
        text("SELECT min(start_at), max(end_at) FROM calendar_windows WHERE plant_code = :p"), p
    ).one()
    if day is None:
        today = datetime.now(zone).date()
        day = (
            today
            if bounds[0] is None or bounds[1].astimezone(zone).date() >= today
            else (bounds[1].astimezone(zone).date())
        )
    start = datetime.combine(day, time(0), zone)
    end = datetime.combine(day + timedelta(days=1), time(0), zone)
    rows = ctx.db.execute(
        text(
            "SELECT id, resource_code, kind, start_at, end_at, covered, "
            "import_id IS NOT NULL AS imported FROM calendar_windows "
            "WHERE plant_code = :p AND start_at < :e AND end_at > :s ORDER BY start_at"
        ),
        {**p, "s": start, "e": end},
    ).all()
    machines = [
        MachineDay(
            resource_code=m.resource_code,
            name=m.name,
            windows=[_window(r, start) for r in rows if r.resource_code == m.resource_code],
        )
        for m in ctx.db.execute(
            text(
                "SELECT resource_code, name FROM resources WHERE plant_code = :p "
                "ORDER BY resource_code"
            ),
            p,
        )
    ]
    exceptions = [
        _window(r, start)
        for r in ctx.db.execute(
            text(
                "SELECT id, resource_code, kind, start_at, end_at, covered, "
                "import_id IS NOT NULL AS imported FROM calendar_windows "
                "WHERE plant_code = :p AND kind IN ('maintenance', 'holiday', 'overtime') "
                "AND end_at > :s AND start_at < :e ORDER BY start_at LIMIT 200"
            ),
            {**p, "s": start, "e": start + timedelta(weeks=12)},
        )
    ]
    overtime = [
        OvertimeOut.model_validate(r._mapping)
        for r in ctx.db.execute(
            text(
                "SELECT resource_code, iso_year, iso_week, overtime_h FROM overtime_worked "
                "WHERE plant_code = :p "
                "ORDER BY iso_year DESC, iso_week DESC, resource_code LIMIT 200"
            ),
            p,
        )
    ]
    return CalendarOut(
        plant_code=plant_code,
        timezone_iana=tz,
        day=day,
        machines=machines,
        exceptions=exceptions,
        data_start_at=bounds[0],
        data_end_at=bounds[1],
        overtime=overtime,
    )


def _machine(ctx: Ctx, plant_code: str, resource_code: str) -> None:
    found = ctx.db.execute(
        text("SELECT 1 FROM resources WHERE plant_code = :p AND resource_code = :r"),
        {"p": plant_code, "r": resource_code},
    ).first()
    if found is None:
        raise ApiProblem("unknown_machine")


def _log(ctx: Ctx, action: str, target: str, detail: str = "") -> None:
    audit(ctx.db, ctx.principal.tenant_id, ctx.principal.actor, action, target, detail)


@router.post("/plants/{plant_code}/calendar/windows", response_model=WindowOut, status_code=201)
def add_window(plant_code: str, body: WindowIn, ctx: Edit, changed: DataChanged) -> WindowOut:
    changed(ctx, plant_code, "calendar")
    body = body.in_zone(ZoneInfo(_plant(ctx, plant_code)))
    _machine(ctx, plant_code, body.resource_code)
    row = ctx.db.execute(
        text(
            "INSERT INTO calendar_windows (tenant_id, plant_code, resource_code, kind, start_at, "
            "end_at, covered) VALUES (:t, :p, :r, :k, :s, :e, :c) "
            "RETURNING id, resource_code, kind, start_at, end_at, covered, "
            "import_id IS NOT NULL AS imported"
        ),
        {
            "t": ctx.principal.tenant_id,
            "p": plant_code,
            "r": body.resource_code,
            "k": body.kind,
            "s": body.start_at,
            "e": body.end_at,
            "c": body.covered,
        },
    ).one()
    _log(
        ctx,
        "calendar_window_added",
        f"{plant_code}/{body.resource_code}",
        f"{body.kind} {body.start_at.isoformat()} - {body.end_at.isoformat()}",
    )
    return _window(row, body.start_at)


@router.patch("/plants/{plant_code}/calendar/windows/{window_id}", response_model=WindowOut)
def set_covered(
    plant_code: str, window_id: int, body: CoveredIn, ctx: Edit, changed: DataChanged
) -> WindowOut:
    """Mark a break as covered: someone keeps the machine running during the break."""
    changed(ctx, plant_code, "calendar")
    _plant(ctx, plant_code)
    row = ctx.db.execute(
        text(
            "UPDATE calendar_windows SET covered = :c, import_id = NULL WHERE id = :i "
            "AND plant_code = :p "
            "AND kind = 'break' RETURNING id, resource_code, kind, start_at, end_at, covered, "
            "import_id IS NOT NULL AS imported"
        ),
        {"c": body.covered, "i": window_id, "p": plant_code},
    ).first()
    if row is None:
        raise ApiProblem("break_not_found")
    _log(
        ctx,
        "break_covered" if body.covered else "break_uncovered",
        f"{plant_code}/{row.resource_code}",
        row.start_at.isoformat(),
    )
    return _window(row, row.start_at)


@router.delete("/plants/{plant_code}/calendar/windows/{window_id}", status_code=204)
def delete_window(
    plant_code: str, window_id: int, ctx: Edit, changed: DataChanged, reason: str | None = None
) -> None:
    """Delete a calendar row. One from an upload needs a reason and stays out of rebuilds."""
    changed(ctx, plant_code, "calendar")
    _plant(ctx, plant_code)
    found = ctx.db.execute(
        text(
            "SELECT resource_code, kind, start_at, end_at, import_id IS NOT NULL AS imported "
            "FROM calendar_windows WHERE id = :i AND plant_code = :p"
        ),
        {"i": window_id, "p": plant_code},
    ).first()
    if found is None:
        raise ApiProblem("window_not_found")
    if found.imported:
        key = [found.resource_code, found.kind, key_text(found.start_at), key_text(found.end_at)]
        record_removal(ctx, plant_code, "calendar_windows", key, reason)
    row = ctx.db.execute(
        text(
            "DELETE FROM calendar_windows WHERE id = :i AND plant_code = :p "
            "RETURNING resource_code, kind, start_at"
        ),
        {"i": window_id, "p": plant_code},
    ).one()
    _log(
        ctx,
        "calendar_window_deleted",
        f"{plant_code}/{row.resource_code}",
        f"{row.kind} {row.start_at.isoformat()}",
    )


@router.put("/plants/{plant_code}/overtime", response_model=OvertimeOut)
def put_overtime(plant_code: str, body: OvertimeIn, ctx: Edit, changed: DataChanged) -> OvertimeOut:
    """Overtime worked on one machine in one ISO week (never per person)."""
    changed(ctx, plant_code, "calendar")
    _plant(ctx, plant_code)
    _machine(ctx, plant_code, body.resource_code)
    ctx.db.execute(
        text(
            "INSERT INTO overtime_worked (tenant_id, plant_code, resource_code, iso_year, "
            "iso_week, "
            "overtime_h) VALUES (:t, :p, :r, :y, :w, :h) ON CONFLICT (tenant_id, plant_code, "
            "resource_code, iso_year, iso_week) DO UPDATE SET overtime_h = EXCLUDED.overtime_h, "
            "import_id = NULL"
        ),
        {
            "t": ctx.principal.tenant_id,
            "p": plant_code,
            "r": body.resource_code,
            "y": body.iso_year,
            "w": body.iso_week,
            "h": body.overtime_h,
        },
    )
    _log(
        ctx,
        "overtime_saved",
        f"{plant_code}/{body.resource_code}",
        f"{body.iso_year}-W{body.iso_week:02d}: {body.overtime_h} h",
    )
    return OvertimeOut(**body.model_dump())
