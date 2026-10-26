"""Automatic refresh (ADR-0010 point 10; CI0004 seq 06).

Every data change asks for the plant's numbers to be calculated again: an import run, a row
fixed, an import deleted, a Setup edit or a Calendar edit. The previous numbers stay shown until
the new ones are ready; every page shows why it is recalculating, when the numbers are from, how
old the data is, and a failed or stuck calculation with a retry.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from sqlalchemy import Connection, text

from cip_api.auth.roles import Decision
from cip_api.auth.sessions import audit
from cip_api.errors import ApiProblem
from cip_api.facts import Reason, queue_facts, start_facts
from cip_api.imports import _role_of
from cip_api.settings import Settings, get_settings
from cip_api.tenancy import Ctx, require

router = APIRouter(tags=["refresh"])

Problem = Literal["no_events", "did_not_finish", "error"]


def _latest_done(db: Connection, plant_code: str) -> uuid.UUID | None:
    found = db.execute(
        text(
            "SELECT import_id FROM imports WHERE plant_code = :p AND status = 'done' "
            "ORDER BY created_at DESC LIMIT 1"
        ),
        {"p": plant_code},
    ).scalar_one_or_none()
    return uuid.UUID(str(found)) if found else None


def refresh_after_change(
    settings: Settings, ctx: Ctx, plant_code: str, reason: Reason, background: BackgroundTasks
) -> None:
    """Ask for a recalculation after a data change. Queued after this request commits, so the
    calculation reads the change; nothing to do for a plant without an import in use."""
    latest = _latest_done(ctx.db, plant_code)
    if latest is None:
        return
    tenant = ctx.principal.tenant_id
    start_facts(ctx.db, tenant, plant_code, latest, reason, ctx.principal.actor)
    background.add_task(queue_facts, settings, tenant, latest)


class Changes:
    """Endpoint helper: ``changed(ctx, plant, "calendar")`` asks for a recalculation."""

    def __init__(self, settings: Settings, background: BackgroundTasks) -> None:
        self.settings, self.background = settings, background

    def __call__(self, ctx: Ctx, plant_code: str, reason: Reason) -> None:
        refresh_after_change(self.settings, ctx, plant_code, reason, self.background)


def _changes(
    settings: Annotated[Settings, Depends(get_settings)], background: BackgroundTasks
) -> Changes:
    return Changes(settings, background)


DataChanged = Annotated[Changes, Depends(_changes)]
"""Every endpoint that changes plant data takes this and calls it (ADR-0010 point 10)."""


class RefreshOut(BaseModel):
    """Where a plant's numbers are, for the banner on every page."""

    plant_code: str
    plant_name: str
    timezone_iana: str
    """Times on the banner are shown in plant local time."""
    status: Literal["none", "calculating", "ready", "failed"]
    """none: no import in use yet. failed includes a calculation that did not finish in time."""
    reason: Reason | None
    """What changed, for 'Recalculating because the calendar changed'."""
    changed_by_role: str | None
    """The role that made that change (never a name): 'by the Planner'."""
    requested_at: datetime | None
    numbers_at: datetime | None
    """When the numbers on the pages were calculated; older than the data while recalculating
    or after a failure."""
    problem: Problem | None
    last_event_at: datetime | None
    """The newest touchpoint in the data in use."""
    data_age_days: int | None
    old_after_days: int
    """From this age the data counts as old: the banner asks for new events."""


def _problem(error: str | None) -> Problem:
    return "no_events" if error == "facts:NoEventsError" else "error"


def plant_refresh(settings: Settings, db: Connection, plant_code: str) -> RefreshOut:
    plant = db.execute(
        text("SELECT name, timezone_iana FROM plants WHERE plant_code = :p"), {"p": plant_code}
    ).one()
    run = db.execute(
        text(
            "SELECT f.status, f.reason, f.requested_at, f.error, f.requested_by FROM fact_runs f "
            "JOIN imports i ON i.import_id = f.import_id "
            "WHERE f.plant_code = :p AND i.status = 'done' ORDER BY i.created_at DESC LIMIT 1"
        ),
        {"p": plant_code},
    ).first()
    numbers_at = db.execute(
        text("SELECT max(finished_at) FROM fact_runs WHERE plant_code = :p"), {"p": plant_code}
    ).scalar_one()
    last = db.execute(
        text("SELECT max(at) FROM operation_events WHERE plant_code = :p"), {"p": plant_code}
    ).scalar_one()
    now = datetime.now(UTC)
    status: Literal["none", "calculating", "ready", "failed"] = run.status if run else "none"
    problem: Problem | None = _problem(run.error) if run and run.status == "failed" else None
    late = now - timedelta(minutes=settings.refresh_timeout_min)
    if run and run.status == "calculating" and run.requested_at < late:
        status, problem = "failed", "did_not_finish"
    return RefreshOut(
        plant_code=plant_code,
        plant_name=plant.name,
        timezone_iana=plant.timezone_iana,
        status=status,
        reason=run.reason if run else None,
        changed_by_role=_role_of(db, run.requested_by) if run and run.requested_by else None,
        requested_at=run.requested_at if run else None,
        numbers_at=numbers_at,
        problem=problem,
        last_event_at=last,
        data_age_days=(now - last).days if last else None,
        old_after_days=settings.data_old_after_days,
    )


@router.get("/refresh-status", response_model=list[RefreshOut])
def refresh_status(
    ctx: Annotated[Ctx, Depends(require())],
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[RefreshOut]:
    """Every plant the signed-in role may see, with where its numbers are."""
    plants = ctx.db.execute(text("SELECT plant_code FROM plants ORDER BY plant_code")).scalars()
    own = ctx.principal.plant_code
    return [plant_refresh(settings, ctx.db, p) for p in plants if own is None or own == p]


@router.post("/plants/{plant_code}/refresh", response_model=RefreshOut, status_code=202)
def retry(
    plant_code: str,
    ctx: Annotated[Ctx, Depends(require(decision=Decision.IMPORT_RUN_DIAGNOSTIC))],
    settings: Annotated[Settings, Depends(get_settings)],
    background: BackgroundTasks,
) -> RefreshOut:
    """Calculate the plant's numbers again, e.g. after a failed or stuck calculation."""
    ctx.check_plant(plant_code)
    if (
        ctx.db.execute(
            text("SELECT 1 FROM plants WHERE plant_code = :p"), {"p": plant_code}
        ).first()
        is None
    ):
        raise ApiProblem("plant_not_found")
    if _latest_done(ctx.db, plant_code) is None:
        raise ApiProblem("refresh_needs_import")
    refresh_after_change(settings, ctx, plant_code, "retry", background)
    audit(
        ctx.db,
        ctx.principal.tenant_id,
        ctx.principal.actor,
        "refresh_retried",
        f"plant:{plant_code}",
    )
    return plant_refresh(settings, ctx.db, plant_code)
