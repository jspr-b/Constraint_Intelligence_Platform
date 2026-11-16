"""The client's corrections to the flow found in the data (CI0005 seq 06).

One document per plant, saved whole by the flow editor. Every save is audit-logged with the
role (never a name) and asks for a recalculation, so the numbers use the flow as shown. The
engine applies the edits (``constraint_engine.flow_edits``); nothing here calculates.
"""

import json
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import Connection, text

from cip_api.auth.roles import Decision
from cip_api.auth.sessions import audit
from cip_api.errors import ApiProblem
from cip_api.facts import _plant
from cip_api.refresh import DataChanged
from cip_api.tenancy import Ctx, require
from constraint_engine.flow_edits import AddedRoute, AddedStep, FlowEdits, Touchpoint

router = APIRouter(tags=["flow"])

Edit = Annotated[Ctx, Depends(require(decision=Decision.EDIT_SETUP_CALENDAR))]
CODE = r"^[A-Z0-9][A-Z0-9-]{1,31}$"
StepKind = Literal["machine", "manual", "check", "transport", "storage", "station", "work_centre"]
Name = Annotated[str, Field(min_length=1, max_length=120)]


class StepAddedIn(BaseModel):
    code: Annotated[str, Field(pattern=r"^NEW-\d{2,4}$")]
    """Codes of added steps start with NEW-, so they never clash with the plant's own."""
    name: Name
    kind: StepKind = "check"
    station_code: str | None = None
    after: str | None = None
    before: str | None = None


class RouteIn(BaseModel):
    from_step: str
    to_step: str


class RouteAddedIn(RouteIn):
    route_id: Annotated[str, Field(min_length=1, max_length=40)]
    estimate_pct: Annotated[int | None, Field(ge=1, le=100)] = None
    """The client's estimate of the share; kept apart from measured shares."""


class RouteNameIn(RouteIn):
    name: Name


class TouchpointIn(RouteIn):
    touchpoint_id: Annotated[str, Field(min_length=1, max_length=40)]
    name: Name
    at: Annotated[float, Field(ge=0.05, le=0.95)] = 0.5


class MergeIn(BaseModel):
    code: str
    into: str


class ParallelIn(BaseModel):
    code: str
    places: Annotated[int, Field(ge=1, le=20)]


class StepNameIn(BaseModel):
    code: str
    name: Name


class StepKindIn(BaseModel):
    code: str
    kind: StepKind


class StationIn(BaseModel):
    code: Annotated[str, Field(pattern=CODE)]
    name: Name


class StepStationIn(BaseModel):
    code: str
    station_code: str | None
    """None: the step has no station."""


class PositionIn(BaseModel):
    id: str
    x: float
    y: float


class FlowEditsDoc(BaseModel):
    """Everything the client changed on the found flow. Layout (positions, stations) is for
    the drawing; the rest is used by the calculation."""

    steps_added: list[StepAddedIn] = []
    routes_added: list[RouteAddedIn] = []
    routes_wrong: list[RouteIn] = []
    route_names: list[RouteNameIn] = []
    touchpoints: list[TouchpointIn] = []
    merges: list[MergeIn] = []
    parallel: list[ParallelIn] = []
    step_names: list[StepNameIn] = []
    step_kinds: list[StepKindIn] = []
    stations_added: list[StationIn] = []
    station_names: list[StationIn] = []
    stations_removed: list[str] = []
    step_stations: list[StepStationIn] = []
    positions: list[PositionIn] = []

    @model_validator(mode="after")
    def _consistent(self) -> "FlowEditsDoc":
        added = [s.code for s in self.steps_added]
        if len(set(added)) != len(added):
            raise ValueError("two added steps have the same code")
        for m in self.merges:
            if m.code == m.into:
                raise ValueError("a step cannot be merged into itself")
        return self


class FlowEditsIn(BaseModel):
    edits: FlowEditsDoc
    version: int
    """The version the editor started from; a save on an older version is refused."""
    change: Annotated[str, Field(min_length=1, max_length=40, pattern=r"^[a-z_]+$")]
    """What changed, as a code for the audit log (e.g. ``step_added``)."""


class FlowEditsOut(BaseModel):
    plant_code: str
    edits: FlowEditsDoc
    version: int
    updated_at: datetime | None
    updated_by_role: str | None


def to_engine(doc: FlowEditsDoc) -> FlowEdits:
    return FlowEdits(
        steps_added=tuple(
            AddedStep(s.code, s.name, s.kind, s.station_code, s.after, s.before)
            for s in doc.steps_added
        ),
        routes_added=tuple(
            AddedRoute(r.route_id, r.from_step, r.to_step, r.estimate_pct) for r in doc.routes_added
        ),
        routes_wrong=frozenset((r.from_step, r.to_step) for r in doc.routes_wrong),
        route_names={(r.from_step, r.to_step): r.name for r in doc.route_names},
        touchpoints=tuple(
            Touchpoint(t.touchpoint_id, t.from_step, t.to_step, t.name, t.at)
            for t in doc.touchpoints
        ),
        merges={m.code: m.into for m in doc.merges},
        parallel={p.code: p.places for p in doc.parallel},
        step_names={n.code: n.name for n in doc.step_names},
        step_kinds={k.code: k.kind for k in doc.step_kinds},
    )


def load_edits(conn: Connection, plant_code: str) -> tuple[FlowEditsDoc, int, object, object]:
    row = conn.execute(
        text(
            "SELECT edits, version, updated_at, updated_by_role FROM flow_edits "
            "WHERE plant_code = :p"
        ),
        {"p": plant_code},
    ).first()
    if row is None:
        return FlowEditsDoc(), 0, None, None
    return (
        FlowEditsDoc.model_validate(json.loads(row.edits)),
        int(row.version),
        row.updated_at,
        row.updated_by_role,
    )


def _codes(conn: Connection, plant_code: str) -> set[str]:
    return {
        str(c)
        for c in conn.execute(
            text("SELECT resource_code FROM resources WHERE plant_code = :p"), {"p": plant_code}
        ).scalars()
    }


@router.get("/plants/{plant_code}/flow/edits", response_model=FlowEditsOut)
def read_edits(plant_code: str, ctx: Annotated[Ctx, Depends(require())]) -> FlowEditsOut:
    _plant(ctx, plant_code)
    doc, version, at, role = load_edits(ctx.db, plant_code)
    return FlowEditsOut(
        plant_code=plant_code,
        edits=doc,
        version=version,
        updated_at=at,  # type: ignore[arg-type]
        updated_by_role=role,  # type: ignore[arg-type]
    )


@router.put("/plants/{plant_code}/flow/edits", response_model=FlowEditsOut)
def save_edits(plant_code: str, body: FlowEditsIn, ctx: Edit, changed: DataChanged) -> FlowEditsOut:
    """Save the client's flow; the numbers are recalculated with it."""
    _plant(ctx, plant_code)
    before, version, _, _ = load_edits(ctx.db, plant_code)
    if body.version != version:
        raise ApiProblem("flow_changed_elsewhere")
    known = _codes(ctx.db, plant_code) | {s.code for s in body.edits.steps_added}
    for m in body.edits.merges:
        if m.code not in known or m.into not in known:
            raise ApiProblem("flow_unknown_step")
    now = datetime.now(UTC)
    role = ctx.principal.role.value
    ctx.db.execute(
        text(
            "INSERT INTO flow_edits (tenant_id, plant_code, edits, version, updated_at, "
            "updated_by_role) VALUES (:t, :p, :e, 1, :now, :r) "
            "ON CONFLICT (tenant_id, plant_code) DO UPDATE SET edits = excluded.edits, "
            "version = flow_edits.version + 1, updated_at = excluded.updated_at, "
            "updated_by_role = excluded.updated_by_role"
        ),
        {
            "t": ctx.principal.tenant_id,
            "p": plant_code,
            "e": body.edits.model_dump_json(),
            "now": now,
            "r": role,
        },
    )
    audit(ctx.db, ctx.principal.tenant_id, ctx.principal.actor, f"flow:{body.change}", plant_code)
    # Moving cards changes the drawing only; anything else changes the numbers.
    if before.model_copy(update={"positions": []}) != body.edits.model_copy(
        update={"positions": []}
    ):
        changed(ctx, plant_code, "flow")
    return FlowEditsOut(
        plant_code=plant_code,
        edits=body.edits,
        version=version + 1,
        updated_at=now,
        updated_by_role=role,
    )
