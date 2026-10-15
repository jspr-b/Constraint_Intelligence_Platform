"""The COO sets who may open, see and decide what (ADR-0007). Every change is audit-logged."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text

from cip_api.auth.access import decision_locked, load_access, page_locked
from cip_api.auth.roles import PAGES, Decision, Money, Plants, Role
from cip_api.auth.sessions import audit
from cip_api.tenancy import Ctx, require

router = APIRouter(prefix="/access", tags=["access"])
View = Annotated[Ctx, Depends(require(page="access"))]
Change = Annotated[Ctx, Depends(require(page="access", decision=Decision.CHANGE_ACCESS))]


class RoleAccessOut(BaseModel):
    role: Role
    start_page: str
    pages: list[str]
    money: Money
    plants: Plants
    decisions: list[Decision]


class AccessOut(BaseModel):
    pages: list[str]
    decisions: list[Decision]
    roles: list[RoleAccessOut]
    locked_pages: dict[Role, list[str]]
    locked_decisions: list[Decision]


class PageIn(BaseModel):
    role: Role
    page: str
    allowed: bool


class DataIn(BaseModel):
    role: Role
    money: Money
    plants: Plants


class DecisionIn(BaseModel):
    role: Role
    decision: Decision
    allowed: bool


def _matrix(ctx: Ctx) -> AccessOut:
    roles = []
    for role in Role:
        a = load_access(ctx.db, role)
        roles.append(
            RoleAccessOut(
                role=role,
                start_page=a.start_page,
                pages=[p for p in PAGES if p in a.pages],
                money=a.money,
                plants=a.plants,
                decisions=[d for d in Decision if d in a.decisions],
            )
        )
    return AccessOut(
        pages=list(PAGES),
        decisions=list(Decision),
        roles=roles,
        locked_pages={r: [p for p in PAGES if page_locked(r, p)] for r in Role},
        locked_decisions=[d for d in Decision if decision_locked(d)],
    )


@router.get("", response_model=AccessOut)
def get_access(ctx: View) -> AccessOut:
    return _matrix(ctx)


@router.put("/pages", response_model=AccessOut)
def set_page(body: PageIn, ctx: Change) -> AccessOut:
    if body.page not in PAGES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown page")
    if page_locked(body.role, body.page):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "this page cannot be turned off for this role"
        )
    before = body.page in load_access(ctx.db, body.role).pages
    ctx.db.execute(
        text(
            "INSERT INTO access_pages (tenant_id, role, page, allowed) VALUES (:t, :r, :p, :a) "
            "ON CONFLICT (tenant_id, role, page) DO UPDATE SET allowed = EXCLUDED.allowed"
        ),
        {"t": ctx.principal.tenant_id, "r": body.role, "p": body.page, "a": body.allowed},
    )
    audit(
        ctx.db,
        ctx.principal.tenant_id,
        ctx.principal.actor,
        "access_page_changed",
        f"{body.role.value}/{body.page}",
        f"{before} -> {body.allowed}",
    )
    return _matrix(ctx)


@router.put("/data", response_model=AccessOut)
def set_data(body: DataIn, ctx: Change) -> AccessOut:
    before = load_access(ctx.db, body.role)
    ctx.db.execute(
        text(
            "INSERT INTO access_data (tenant_id, role, money, plants) VALUES (:t, :r, :m, :p) "
            "ON CONFLICT (tenant_id, role) DO UPDATE "
            "SET money = EXCLUDED.money, plants = EXCLUDED.plants"
        ),
        {"t": ctx.principal.tenant_id, "r": body.role, "m": body.money, "p": body.plants},
    )
    audit(
        ctx.db,
        ctx.principal.tenant_id,
        ctx.principal.actor,
        "access_data_changed",
        body.role.value,
        f"money {before.money.value} -> {body.money.value}, "
        f"plants {before.plants.value} -> {body.plants.value}",
    )
    return _matrix(ctx)


@router.put("/decisions", response_model=AccessOut)
def set_decision(body: DecisionIn, ctx: Change) -> AccessOut:
    if decision_locked(body.decision):
        raise HTTPException(status.HTTP_409_CONFLICT, "this decision cannot be reassigned")
    before = body.decision in load_access(ctx.db, body.role).decisions
    ctx.db.execute(
        text(
            "INSERT INTO access_decisions (tenant_id, role, decision, allowed) "
            "VALUES (:t, :r, :d, :a) ON CONFLICT (tenant_id, role, decision) "
            "DO UPDATE SET allowed = EXCLUDED.allowed"
        ),
        {"t": ctx.principal.tenant_id, "r": body.role, "d": body.decision, "a": body.allowed},
    )
    audit(
        ctx.db,
        ctx.principal.tenant_id,
        ctx.principal.actor,
        "access_decision_changed",
        f"{body.role.value}/{body.decision.value}",
        f"{before} -> {body.allowed}",
    )
    return _matrix(ctx)
