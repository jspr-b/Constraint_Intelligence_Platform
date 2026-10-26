"""Getting-started progress: where a client stands between sign-in and the answer.

Every step's state comes from the data (plants, the latest import and its report), never from
clicks. The web app shows it as a short checklist until every available step is done.
"""

import json
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text

from cip_api.auth.roles import Decision, Role
from cip_api.tenancy import Ctx, require

router = APIRouter(tags=["getting started"])

StepKey = Literal["plant", "upload", "check", "answer"]
StepState = Literal["done", "todo", "later"]


class StepOut(BaseModel):
    key: StepKey
    state: StepState
    detail: str | None = None
    """Why a step is not done yet (``uploaded``, ``running``, ``failed``, ``calculating``,
    ``numbers_failed``, ``missing``), or for a
    done ``check``, ``confirm``: items a person should confirm, or ``optional``: files that would
    add euros or confidence."""
    missing: list[str] = []
    """For ``check``: the minimum-set items missing or to confirm, or the optional files not sent
    (keys such as ``events`` or ``orders``)."""


class OnboardingOut(BaseModel):
    plant_code: str | None
    plant_name: str | None
    steps: list[StepOut]
    next_step: StepKey | None
    complete: bool
    """Every step that is available now is done."""
    can_set_up: bool
    """The signed-in role may add plants and run imports."""
    setup_contacts: list[str]
    """Who can do the setup steps (active IT accounts), for roles that have to wait."""


def _latest_import(ctx: Ctx, plant_code: str) -> Any:
    return ctx.db.execute(
        text(
            "SELECT i.status, i.report, f.status AS facts_status, "
            "f.finished_at AS numbers_at FROM imports i "
            "LEFT JOIN fact_runs f ON f.import_id = i.import_id "
            "WHERE i.plant_code = :p AND i.status <> 'deleted' ORDER BY i.created_at DESC LIMIT 1"
        ),
        {"p": plant_code},
    ).first()


def _upload_step(latest: Any) -> StepOut:
    if latest is None:
        return StepOut(key="upload", state="todo")
    if latest.status == "done":
        # The import is stored; the step is done once its numbers are calculated. A later
        # recalculation (ADR-0010 point 10) keeps it done: the banner on every page tells.
        if latest.facts_status == "ready" or latest.numbers_at is not None:
            return StepOut(key="upload", state="done")
        if latest.facts_status == "calculating":
            return StepOut(key="upload", state="todo", detail="calculating")
        return StepOut(key="upload", state="todo", detail="numbers_failed")
    return StepOut(key="upload", state="todo", detail=latest.status)


def _check_step(latest: Any) -> StepOut:
    if latest is None or latest.status != "done" or not latest.report:
        return StepOut(key="check", state="todo")
    report = json.loads(latest.report)
    missing = [
        m["key"] for m in report.get("minimum_set", []) if m["status"] in ("missing", "partial")
    ]
    if missing:
        return StepOut(key="check", state="todo", detail="missing", missing=missing)
    confirm = [m["key"] for m in report.get("minimum_set", []) if m["status"] == "check"]
    if confirm:
        # Enough to diagnose; a person should still confirm these (e.g. no holidays listed).
        return StepOut(key="check", state="done", detail="confirm", missing=confirm)
    optional = [
        m["key"] for m in report.get("optional_set", []) if m["status"] in ("missing", "partial")
    ]
    if optional:
        # Enough to diagnose; these would add euros, actions or confidence (ADR-0009).
        return StepOut(key="check", state="done", detail="optional", missing=optional)
    return StepOut(key="check", state="done")


def _answer_step(ctx: Ctx, plant_code: str) -> StepOut:
    """Done once the facts job has saved the plant's constraint for its whole period."""
    found = ctx.db.execute(
        text("SELECT 1 FROM detections WHERE plant_code = :p AND period_kind = 'all'"),
        {"p": plant_code},
    ).first()
    return StepOut(key="answer", state="done" if found else "todo")


def onboarding_steps(ctx: Ctx, plant_code: str | None) -> list[StepOut]:
    if plant_code is None:
        return [
            StepOut(key="plant", state="todo"),
            StepOut(key="upload", state="todo"),
            StepOut(key="check", state="todo"),
            StepOut(key="answer", state="todo"),
        ]
    latest = _latest_import(ctx, plant_code)
    return [
        StepOut(key="plant", state="done"),
        _upload_step(latest),
        _check_step(latest),
        _answer_step(ctx, plant_code),
    ]


@router.get("/onboarding", response_model=OnboardingOut)
def onboarding(
    ctx: Annotated[Ctx, Depends(require())], plant_code: str | None = None
) -> OnboardingOut:
    """Progress for ``plant_code``, or for the first plant this role may see."""
    plants = [
        r
        for r in ctx.db.execute(text("SELECT plant_code, name FROM plants ORDER BY name"))
        if ctx.can_see_plant(r.plant_code)
    ]
    chosen = next((p for p in plants if p.plant_code == plant_code), plants[0] if plants else None)
    steps = onboarding_steps(ctx, chosen.plant_code if chosen else None)
    todo = [s.key for s in steps if s.state == "todo"]
    contacts = ctx.db.execute(
        text("SELECT email FROM users WHERE role = :r AND status = 'active' ORDER BY email"),
        {"r": Role.IT.value},
    )
    return OnboardingOut(
        plant_code=chosen.plant_code if chosen else None,
        plant_name=chosen.name if chosen else None,
        steps=steps,
        next_step=todo[0] if todo else None,
        complete=not todo,
        can_set_up=Decision.IMPORT_RUN_DIAGNOSTIC in ctx.access.decisions,
        setup_contacts=[r.email for r in contacts],
    )
