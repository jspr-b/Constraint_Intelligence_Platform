"""Sign in, sign out and who-am-I.

People sign in with the company identity provider (OIDC) or, in dev, with the dev login.
Stations sign in with machine + PIN; the session belongs to the machine.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import Connection, text

from cip_api.auth.access import load_access
from cip_api.auth.oidc import OidcError, verify_id_token
from cip_api.auth.pins import verify_pin
from cip_api.auth.roles import Role
from cip_api.auth.sessions import (
    COOKIE,
    Principal,
    audit,
    find_session,
    start_session,
    tenant_conn,
    token_hash,
)
from cip_api.settings import Settings, get_settings
from cip_api.tenancy import current_principal, tenant_db

router = APIRouter(prefix="/auth", tags=["auth"])
SettingsDep = Annotated[Settings, Depends(get_settings)]


class DevLoginIn(BaseModel):
    tenant_id: uuid.UUID
    email: str


class OidcLoginIn(BaseModel):
    tenant_id: uuid.UUID
    id_token: str


class StationLoginIn(BaseModel):
    tenant_id: uuid.UUID
    plant_code: str
    resource_code: str
    pin: str = Field(min_length=4, max_length=8)


class AuthConfigOut(BaseModel):
    provider: str
    """``dev`` (email sign-in, pilots only) or ``oidc`` (company account via Keycloak)."""
    tenant_name: str | None


class StationChoiceOut(BaseModel):
    plant_code: str
    resource_code: str
    resource_name: str | None


class MeOut(BaseModel):
    tenant_id: uuid.UUID
    subject_type: str
    subject_id: str
    role: Role
    plant_code: str | None
    resource_code: str | None
    start_page: str
    pages: list[str]
    money: str
    plants: str
    decisions: list[str]


@router.get("/config", response_model=AuthConfigOut)
def auth_config(tenant_id: uuid.UUID, settings: SettingsDep) -> AuthConfigOut:
    """What the sign-in page shows. Public: reveals only the tenant's display name."""
    provider = "dev" if settings.env == "dev" and settings.auth_provider == "dev" else "oidc"
    with tenant_conn(settings, tenant_id) as conn:
        name = conn.execute(text("SELECT name FROM tenants WHERE id = :t"), {"t": tenant_id})
        return AuthConfigOut(provider=provider, tenant_name=name.scalar_one_or_none())


@router.get("/stations", response_model=list[StationChoiceOut])
def station_choices(tenant_id: uuid.UUID, settings: SettingsDep) -> list[StationChoiceOut]:
    """Machines with an active station login, for the 'Which station is this?' picker."""
    with tenant_conn(settings, tenant_id) as conn:
        rows = conn.execute(
            text(
                "SELECT s.plant_code, s.resource_code, r.name AS resource_name "
                "FROM station_logins s LEFT JOIN resources r "
                "ON r.plant_code = s.plant_code AND r.resource_code = s.resource_code "
                "WHERE s.status = 'active' ORDER BY s.plant_code, s.resource_code"
            )
        )
        return [StationChoiceOut.model_validate(r._mapping) for r in rows]


def _sign_in_user(settings: Settings, tenant: uuid.UUID, email: str, response: Response) -> None:
    with tenant_conn(settings, tenant) as conn:
        user = conn.execute(
            text("SELECT user_id, role, plant_code, status FROM users WHERE email = :e"),
            {"e": email.lower()},
        ).first()
        if user is None or user.status == "disabled":
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "no active account for this email")
        if user.status == "invited":
            conn.execute(
                text("UPDATE users SET status = 'active' WHERE user_id = :u"), {"u": user.user_id}
            )
        who = Principal(tenant, "user", str(user.user_id), Role(user.role), user.plant_code)
        start_session(conn, settings, who, response)
        audit(conn, tenant, who.actor, "sign_in", f"user:{user.user_id}")


@router.post("/dev-login", status_code=204)
def dev_login(body: DevLoginIn, settings: SettingsDep, response: Response) -> None:
    """Pilot-only sign-in by email, for an account IT created. Not available outside dev."""
    if settings.env != "dev" or settings.auth_provider != "dev":
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    _sign_in_user(settings, body.tenant_id, body.email, response)


@router.post("/oidc-login", status_code=204)
def oidc_login(body: OidcLoginIn, settings: SettingsDep, response: Response) -> None:
    if settings.auth_provider != "oidc":
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    try:
        email = verify_id_token(settings, body.id_token)
    except OidcError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    _sign_in_user(settings, body.tenant_id, email, response)


@router.post("/station-login", status_code=204)
def station_login(body: StationLoginIn, settings: SettingsDep, response: Response) -> None:
    """Machine + PIN. Wrong PINs count up; at the limit the login locks until IT enables it."""
    with tenant_conn(settings, body.tenant_id) as conn:
        login = conn.execute(
            text(
                "SELECT station_login_id, pin_hash, status, failed_attempts FROM station_logins "
                "WHERE plant_code = :p AND resource_code = :r"
            ),
            {"p": body.plant_code, "r": body.resource_code},
        ).first()
        if login is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "station or PIN not recognised")
        target = f"station:{login.station_login_id}"
        if login.status != "active":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "station login is off; ask IT")
        if verify_pin(body.pin, login.pin_hash):
            conn.execute(
                text("UPDATE station_logins SET failed_attempts = 0 WHERE station_login_id = :s"),
                {"s": login.station_login_id},
            )
            who = Principal(
                body.tenant_id,
                "station",
                str(login.station_login_id),
                Role.STATION,
                body.plant_code,
                body.resource_code,
            )
            start_session(conn, settings, who, response)
            audit(conn, body.tenant_id, who.actor, "sign_in", target)
            return
        failed = login.failed_attempts + 1
        locked = failed >= settings.pin_max_attempts
        conn.execute(
            text(
                "UPDATE station_logins SET failed_attempts = :f, "
                "status = CASE WHEN :locked THEN 'locked' ELSE status END "
                "WHERE station_login_id = :s"
            ),
            {"f": failed, "locked": locked, "s": login.station_login_id},
        )
        if locked:
            audit(
                conn, body.tenant_id, target, "station_login_locked", target, f"{failed} wrong PINs"
            )
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "station or PIN not recognised")


@router.post("/logout", status_code=204)
def logout(request: Request, settings: SettingsDep, response: Response) -> None:
    token = request.cookies.get(COOKIE)
    if token:
        who = find_session(settings, token)
        if who is not None:
            with tenant_conn(settings, who.tenant_id) as conn:
                conn.execute(
                    text("DELETE FROM sessions WHERE token_hash = :h"), {"h": token_hash(token)}
                )
                audit(conn, who.tenant_id, who.actor, "sign_out", who.actor)
    response.delete_cookie(COOKIE, path="/")


@router.get("/me", response_model=MeOut)
def me(
    principal: Annotated[Principal, Depends(current_principal)],
    db: Annotated[Connection, Depends(tenant_db)],
) -> MeOut:
    access = load_access(db, principal.role)
    return MeOut(
        tenant_id=principal.tenant_id,
        subject_type=principal.subject_type,
        subject_id=principal.subject_id,
        role=principal.role,
        plant_code=principal.plant_code,
        resource_code=principal.resource_code,
        start_page=access.start_page,
        pages=sorted(access.pages),
        money=access.money.value,
        plants=access.plants.value,
        decisions=sorted(d.value for d in access.decisions),
    )
