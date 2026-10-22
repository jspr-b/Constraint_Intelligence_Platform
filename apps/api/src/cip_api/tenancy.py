"""Who is asking, and in which tenant (ADR-0004, ADR-0007).

Tenant and role come from the session cookie. Only when ``CIP_ENV=dev`` and no cookie is sent,
the ``X-Tenant-Id`` header (with optional ``X-Role`` and ``X-Plant``) stands in for a session.
Every request runs in a transaction with ``app.tenant_id`` set, so row-level security applies.
"""

import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy import Connection

from cip_api.auth.access import Access, load_access
from cip_api.auth.roles import Decision, Plants, Role
from cip_api.auth.sessions import COOKIE, Principal, find_session, tenant_conn
from cip_api.errors import ApiProblem
from cip_api.settings import Settings, get_settings


def current_principal(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    x_tenant_id: Annotated[str | None, Header()] = None,
    x_role: Annotated[str | None, Header()] = None,
    x_plant: Annotated[str | None, Header()] = None,
) -> Principal:
    token = request.cookies.get(COOKIE)
    if token:
        principal = find_session(settings, token)
        if principal is None:
            raise ApiProblem("session_expired")
        return principal
    if settings.env != "dev":
        raise ApiProblem("sign_in_required")
    if x_tenant_id is None:
        raise ApiProblem("dev_header_required")
    try:
        tenant = uuid.UUID(x_tenant_id)
        role = Role(x_role or Role.COO)
    except ValueError as exc:
        raise ApiProblem("dev_header_invalid") from exc
    return Principal(tenant, "dev", "header", role, plant_code=x_plant)


def current_tenant(principal: Annotated[Principal, Depends(current_principal)]) -> uuid.UUID:
    return principal.tenant_id


def tenant_db(
    principal: Annotated[Principal, Depends(current_principal)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Iterator[Connection]:
    """A connection in a transaction with the tenant set (SET LOCAL semantics).

    Depend on it with ``scope="function"``: the transaction then commits before the response is
    sent, so a client that acts on the response (upload, then run) always finds the row.
    """
    with tenant_conn(settings, principal.tenant_id) as conn:
        yield conn


@dataclass(frozen=True, slots=True)
class Ctx:
    """The signed-in principal, their effective access and a tenant-scoped connection."""

    principal: Principal
    access: Access
    db: Connection

    def can_see_plant(self, plant_code: str) -> bool:
        return self.access.plants is Plants.ALL or plant_code == self.principal.plant_code

    def check_plant(self, plant_code: str) -> None:
        if not self.can_see_plant(plant_code):
            raise ApiProblem("own_plant_only")


def require(page: str | None = None, decision: Decision | None = None) -> Callable[..., Ctx]:
    """Endpoint dependency: the role must be allowed to open ``page`` and take ``decision``."""

    def dependency(
        principal: Annotated[Principal, Depends(current_principal)],
        db: Annotated[Connection, Depends(tenant_db, scope="function")],
    ) -> Ctx:
        access = load_access(db, principal.role)
        if page is not None and page not in access.pages:
            raise ApiProblem("page_not_allowed")
        if decision is not None and decision not in access.decisions:
            raise ApiProblem("decision_not_allowed")
        return Ctx(principal, access, db)

    return dependency
