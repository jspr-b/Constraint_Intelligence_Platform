"""Accounts, managed by IT (ADR-0007). Every change lands in the audit log.

Personal accounts are for people who plan, decide or administer. Floor screens use station
logins, which belong to a machine and carry no name (ADR-0005).
"""

import re
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from cip_api.auth.pins import hash_pin, valid_pin
from cip_api.auth.roles import Decision, Role
from cip_api.auth.sessions import audit, end_sessions
from cip_api.tenancy import Ctx, require

router = APIRouter(tags=["users"])
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
View = Annotated[Ctx, Depends(require(page="users"))]
Manage = Annotated[Ctx, Depends(require(page="users", decision=Decision.MANAGE_LOGINS))]


class UserOut(BaseModel):
    user_id: uuid.UUID
    email: str
    role: Role
    plant_code: str | None
    status: str


class StationLoginOut(BaseModel):
    station_login_id: uuid.UUID
    plant_code: str
    resource_code: str
    status: str


class AccountsOut(BaseModel):
    users: list[UserOut]
    station_logins: list[StationLoginOut]


class InviteIn(BaseModel):
    email: str
    role: Role
    plant_code: str | None = None

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        if not EMAIL.fullmatch(v):
            raise ValueError("not an email address")
        return v.lower()

    @field_validator("role")
    @classmethod
    def _person(cls, v: Role) -> Role:
        if v is Role.STATION:
            raise ValueError("stations get a station login, not a personal account")
        return v


class PinIn(BaseModel):
    pin: str = Field(min_length=4, max_length=8)

    @field_validator("pin")
    @classmethod
    def _pin(cls, v: str) -> str:
        if not valid_pin(v):
            raise ValueError("PIN is 4 to 8 digits")
        return v


class StationLoginIn(PinIn):
    plant_code: str
    resource_code: str


class AuditOut(BaseModel):
    at: datetime
    actor: str
    action: str
    target: str
    detail: str


@router.get("/users", response_model=AccountsOut)
def list_accounts(ctx: View) -> AccountsOut:
    users = ctx.db.execute(
        text("SELECT user_id, email, role, plant_code, status FROM users ORDER BY email")
    )
    stations = ctx.db.execute(
        text(
            "SELECT station_login_id, plant_code, resource_code, status FROM station_logins "
            "ORDER BY plant_code, resource_code"
        )
    )
    return AccountsOut(
        users=[UserOut.model_validate(r._mapping) for r in users],
        station_logins=[StationLoginOut.model_validate(r._mapping) for r in stations],
    )


@router.post("/users", response_model=UserOut, status_code=201)
def invite(body: InviteIn, ctx: Manage) -> UserOut:
    if body.plant_code is not None:
        _check_plant(ctx, body.plant_code)
    try:
        with ctx.db.begin_nested():
            row = ctx.db.execute(
                text(
                    "INSERT INTO users (tenant_id, email, role, plant_code) "
                    "VALUES (:t, :e, :r, :p) RETURNING user_id, email, role, plant_code, status"
                ),
                {
                    "t": ctx.principal.tenant_id,
                    "e": body.email,
                    "r": body.role,
                    "p": body.plant_code,
                },
            ).one()
    except IntegrityError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "an account with this email exists") from exc
    audit(
        ctx.db,
        ctx.principal.tenant_id,
        ctx.principal.actor,
        "user_invited",
        f"user:{row.user_id}",
        f"role={body.role.value}",
    )
    return UserOut.model_validate(row._mapping)


def _set_user_status(ctx: Ctx, user_id: uuid.UUID, new: str) -> UserOut:
    if new == "disabled" and ctx.principal.subject_id == str(user_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "you cannot disable your own account")
    row = ctx.db.execute(
        text(
            "UPDATE users SET status = :s WHERE user_id = :u "
            "RETURNING user_id, email, role, plant_code, status"
        ),
        {"s": new, "u": user_id},
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    if new == "disabled":
        end_sessions(ctx.db, "user", str(user_id))
    audit(
        ctx.db,
        ctx.principal.tenant_id,
        ctx.principal.actor,
        "user_disabled" if new == "disabled" else "user_enabled",
        f"user:{user_id}",
    )
    return UserOut.model_validate(row._mapping)


@router.post("/users/{user_id}/disable", response_model=UserOut)
def disable_user(user_id: uuid.UUID, ctx: Manage) -> UserOut:
    return _set_user_status(ctx, user_id, "disabled")


@router.post("/users/{user_id}/enable", response_model=UserOut)
def enable_user(user_id: uuid.UUID, ctx: Manage) -> UserOut:
    return _set_user_status(ctx, user_id, "active")


def _check_plant(ctx: Ctx, plant_code: str) -> None:
    found = ctx.db.execute(
        text("SELECT 1 FROM plants WHERE plant_code = :p"), {"p": plant_code}
    ).first()
    if found is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown plant")


@router.post("/station-logins", response_model=StationLoginOut, status_code=201)
def add_station_login(body: StationLoginIn, ctx: Manage) -> StationLoginOut:
    machine = ctx.db.execute(
        text("SELECT 1 FROM resources WHERE plant_code = :p AND resource_code = :r"),
        {"p": body.plant_code, "r": body.resource_code},
    ).first()
    if machine is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown machine for this plant")
    try:
        with ctx.db.begin_nested():
            row = ctx.db.execute(
                text(
                    "INSERT INTO station_logins (tenant_id, plant_code, resource_code, pin_hash) "
                    "VALUES (:t, :p, :r, :h) "
                    "RETURNING station_login_id, plant_code, resource_code, status"
                ),
                {
                    "t": ctx.principal.tenant_id,
                    "p": body.plant_code,
                    "r": body.resource_code,
                    "h": hash_pin(body.pin),
                },
            ).one()
    except IntegrityError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "this machine has a station login") from exc
    audit(
        ctx.db,
        ctx.principal.tenant_id,
        ctx.principal.actor,
        "station_login_added",
        f"station:{row.station_login_id}",
        f"{body.plant_code}/{body.resource_code}",
    )
    return StationLoginOut.model_validate(row._mapping)


def _update_station(
    ctx: Ctx, login_id: uuid.UUID, sql: str, params: dict[str, object], action: str
) -> StationLoginOut:
    row = ctx.db.execute(
        text(
            f"UPDATE station_logins SET {sql} WHERE station_login_id = :id "
            "RETURNING station_login_id, plant_code, resource_code, status"
        ),
        {"id": login_id, **params},
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "station login not found")
    if action == "station_login_disabled":
        end_sessions(ctx.db, "station", str(login_id))
    audit(ctx.db, ctx.principal.tenant_id, ctx.principal.actor, action, f"station:{login_id}")
    return StationLoginOut.model_validate(row._mapping)


@router.post("/station-logins/{login_id}/disable", response_model=StationLoginOut)
def disable_station_login(login_id: uuid.UUID, ctx: Manage) -> StationLoginOut:
    return _update_station(ctx, login_id, "status = 'disabled'", {}, "station_login_disabled")


@router.post("/station-logins/{login_id}/enable", response_model=StationLoginOut)
def enable_station_login(login_id: uuid.UUID, ctx: Manage) -> StationLoginOut:
    """Also unlocks a login locked by wrong PINs."""
    return _update_station(
        ctx, login_id, "status = 'active', failed_attempts = 0", {}, "station_login_enabled"
    )


@router.post("/station-logins/{login_id}/pin", response_model=StationLoginOut)
def reset_station_pin(login_id: uuid.UUID, body: PinIn, ctx: Manage) -> StationLoginOut:
    return _update_station(
        ctx,
        login_id,
        "pin_hash = :h, failed_attempts = 0",
        {"h": hash_pin(body.pin)},
        "station_pin_reset",
    )


@router.get("/audit", response_model=list[AuditOut])
def audit_log(ctx: View, limit: int = 200) -> list[AuditOut]:
    rows = ctx.db.execute(
        text(
            "SELECT at, actor, action, target, detail FROM audit_log "
            "ORDER BY at DESC, id DESC LIMIT :n"
        ),
        {"n": max(1, min(limit, 1000))},
    )
    return [AuditOut.model_validate(r._mapping) for r in rows]
