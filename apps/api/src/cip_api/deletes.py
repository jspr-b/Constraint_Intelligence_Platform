"""Delete an upload, an import or all data of a plant (ADR-0010 point 9; CI0004 seq 05).

Deleted means gone: the import's files, its rows, its corrections, facts and detections are
removed, not hidden. One line stays in the history (and the audit log): who deleted it, when,
and which files it had. Deleting an import that is in use rebuilds the plant from the other
imports and recalculates the answer; the confirmation first shows what will change.
"""

import json
import shutil
import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Response
from pydantic import BaseModel
from sqlalchemy import Connection, text

from cip_api.auth.roles import Role
from cip_api.auth.sessions import audit
from cip_api.corrections import NO_IMPORT, rebuild_and_refresh
from cip_api.db.plant_store import TABLES, load_plant_from_db, merge_imports, rebuild_plant_data
from cip_api.errors import ApiProblem
from cip_api.imports import (
    ListChangeOut,
    PreviewWarningOut,
    Run,
    _row,
    import_dir,
    kept_imports,
)
from cip_api.settings import Settings, get_settings
from cip_api.tenancy import Ctx, require
from constraint_engine.io.compare import compare_plants

router = APIRouter(tags=["imports"])

OWN_ROWS = ("corrections", "facts", "detections", "fact_runs")
"""Tables whose rows belong to one import and go with it."""


class ListSourceOut(BaseModel):
    name: str
    """The list (steps list, shift sheet…), as the import report names it."""
    from_import_id: uuid.UUID | None
    from_created_at: datetime | None
    """The upload the list comes from after the delete; None when no upload has it any more."""


class DeletePreviewOut(BaseModel):
    """What deleting this import changes, from the engine's comparison (nothing is changed)."""

    in_use: bool
    """False for an upload that never ran, failed or was replaced: the data in use stays."""
    events_before: int
    events_after: int
    events_removed: int
    period_before: tuple[datetime | None, datetime | None]
    period_after: tuple[datetime | None, datetime | None]
    lists: list[ListChangeOut]
    lists_after: list[ListSourceOut]
    warnings: list[PreviewWarningOut]
    corrections: int
    """Rows fixed or left out in this import; they are deleted with it."""
    falls_back_to: uuid.UUID | None
    """The earlier version that comes back in use when this new version is deleted."""
    imports_left: int
    """Imports in use after the delete; 0 leaves an empty plant."""


def _busy(db: Connection, plant: str) -> None:
    """Nothing is deleted while an import runs or the plant's numbers are being calculated."""
    if db.execute(
        text("SELECT 1 FROM imports WHERE plant_code = :p AND status = 'running'"), {"p": plant}
    ).first():
        raise ApiProblem("import_running")
    if db.execute(
        text(
            "SELECT 1 FROM fact_runs WHERE plant_code = :p AND status = 'calculating' "
            "AND started_at > now() - interval '15 minutes'"
        ),
        {"p": plant},
    ).first():
        raise ApiProblem("facts_calculating")


def _deletable(ctx: Ctx, import_id: uuid.UUID) -> Any:
    row = _row(ctx.db, import_id)
    ctx.check_plant(row.plant_code)
    if row.status == "deleted":
        raise ApiProblem("import_already_deleted")
    if row.status == "running":
        raise ApiProblem("import_running")
    return row


def _take_out(db: Connection, row: Any) -> uuid.UUID | None:
    """Mark the import deleted; a deleted new version gives its place back to the version it
    replaced. Returns that version."""
    db.execute(
        text("UPDATE imports SET status = 'deleted' WHERE import_id = :i"), {"i": row.import_id}
    )
    if row.status != "done" or row.replaces is None:
        return None
    back = db.execute(
        text(
            "UPDATE imports SET status = 'done' WHERE import_id = :r AND status = 'replaced' "
            "RETURNING import_id"
        ),
        {"r": row.replaces},
    ).scalar_one_or_none()
    return uuid.UUID(str(back)) if back else None


def _in_use(db: Connection, plant: str) -> int:
    return int(
        db.execute(
            text("SELECT count(*) FROM imports WHERE plant_code = :p AND status = 'done'"),
            {"p": plant},
        ).scalar_one()
    )


@router.get("/imports/{import_id}/delete-preview", response_model=DeletePreviewOut)
def delete_preview(
    import_id: uuid.UUID,
    ctx: Annotated[Ctx, Depends(require(page="import"))],
    settings: Annotated[Settings, Depends(get_settings)],
) -> DeletePreviewOut:
    """Rebuild the plant without this import in a transaction that is rolled back, and compare."""
    row = _deletable(ctx, import_id)
    tenant = ctx.principal.tenant_id
    corrections = int(
        ctx.db.execute(
            text("SELECT count(*) FROM corrections WHERE import_id = :i AND undone_at IS NULL"),
            {"i": import_id},
        ).scalar_one()
    )
    before = load_plant_from_db(ctx.db, tenant, row.plant_code)
    trial = ctx.db.begin_nested()
    try:
        back = _take_out(ctx.db, row)
        left = _in_use(ctx.db, row.plant_code)
        lists_after: list[ListSourceOut] = []
        if row.status == "done":
            ctx.db.execute(text("DELETE FROM corrections WHERE import_id = :i"), {"i": import_id})
            merged = merge_imports(
                kept_imports(settings, ctx.db, tenant, row.plant_code, NO_IMPORT)
            )
            rebuild_plant_data(ctx.db, tenant, row.plant_code, merged)
            created: dict[uuid.UUID, datetime] = {
                r.import_id: r.created_at
                for r in ctx.db.execute(
                    text("SELECT import_id, created_at FROM imports WHERE plant_code = :p"),
                    {"p": row.plant_code},
                )
            }
            lists_after = [
                ListSourceOut(name=n, from_import_id=i, from_created_at=created.get(i))
                for n, i in sorted(merged.lists_from.items())
            ]
        after = load_plant_from_db(ctx.db, tenant, row.plant_code)
    finally:
        trial.rollback()
    p = compare_plants(before, after)
    return DeletePreviewOut(
        in_use=row.status == "done",
        events_before=p.events_before,
        events_after=p.events_after,
        events_removed=p.events_removed,
        period_before=p.period_before,
        period_after=p.period_after,
        lists=[
            ListChangeOut(
                name=c.name, before=c.before, after=c.after, new=list(c.new), gone=list(c.gone)
            )
            for c in p.lists
        ],
        lists_after=lists_after,
        warnings=[
            PreviewWarningOut(code=w.code, items=list(w.items), count=w.count)  # type: ignore[arg-type]
            for w in p.warnings
        ],
        corrections=corrections,
        falls_back_to=back,
        imports_left=left,
    )


def _forget(ctx: Ctx, row: Any) -> None:
    """Remove everything of the import but its history line: rows, corrections, numbers, the
    file checks (they hold example values) and the report. Only file names and sizes stay."""
    for table in OWN_ROWS:
        ctx.db.execute(text(f"DELETE FROM {table} WHERE import_id = :i"), {"i": row.import_id})
    names = [
        {"name": f["name"], "size_bytes": f.get("size_bytes", 0)} for f in json.loads(row.files)
    ]
    ctx.db.execute(
        text(
            "UPDATE imports SET files = :f, report = NULL, error = NULL, deleted_at = now(), "
            "deleted_by = :a WHERE import_id = :i"
        ),
        {"f": json.dumps(names), "a": ctx.principal.actor, "i": row.import_id},
    )


@router.delete("/imports/{import_id}", status_code=204)
def delete_import(
    import_id: uuid.UUID,
    ctx: Run,
    settings: Annotated[Settings, Depends(get_settings)],
    background: BackgroundTasks,
) -> Response:
    """Delete an upload or an import for real. One in use: the plant is rebuilt from the rest
    and the answer recalculated; an earlier version it replaced comes back in use."""
    row = _deletable(ctx, import_id)
    if row.status == "done":  # the plant is rebuilt: not while it changes or is calculated
        _busy(ctx.db, row.plant_code)
    tenant = ctx.principal.tenant_id
    events = ctx.db.execute(
        text("SELECT count(*) FROM operation_events WHERE import_id = :i"), {"i": import_id}
    ).scalar_one()
    _take_out(ctx.db, row)
    _forget(ctx, row)
    if row.status == "done":
        rebuild_and_refresh(settings, ctx, row.plant_code, background, "delete")
    audit(
        ctx.db,
        tenant,
        ctx.principal.actor,
        "import_deleted",
        f"import:{import_id}",
        f"{row.plant_code}: upload of {row.created_at:%Y-%m-%d %H:%M} UTC, "
        f"{len(json.loads(row.files))} files, {events} events in use",
    )
    # The files go once the delete is committed; a failed request leaves them in place.
    folder = import_dir(settings, tenant, row.plant_code, import_id)
    background.add_task(shutil.rmtree, folder, ignore_errors=True)
    return Response(status_code=204)


@router.delete("/plants/{plant_code}/data", status_code=204)
def delete_plant_data(
    plant_code: str,
    confirm: str,
    ctx: Annotated[Ctx, Depends(require(page="import"))],
    settings: Annotated[Settings, Depends(get_settings)],
    background: BackgroundTasks,
) -> Response:
    """Delete every import, file and row of a plant (IT only, the plant code typed to confirm).
    The plant itself, its accounts and station logins stay; the history keeps a line per
    import."""
    ctx.check_plant(plant_code)
    if ctx.principal.role != Role.IT:
        raise ApiProblem("plant_delete_it_only")
    if (
        ctx.db.execute(
            text("SELECT 1 FROM plants WHERE plant_code = :p"), {"p": plant_code}
        ).first()
        is None
    ):
        raise ApiProblem("plant_not_found")
    if confirm.strip() != plant_code:
        raise ApiProblem("plant_delete_confirm", plant=plant_code)
    _busy(ctx.db, plant_code)
    tenant = ctx.principal.tenant_id
    rows = ctx.db.execute(
        text("SELECT import_id, files FROM imports WHERE plant_code = :p AND status <> 'deleted'"),
        {"p": plant_code},
    ).all()
    for table in (*TABLES.values(), "corrections", "facts", "detections", "fact_runs"):
        ctx.db.execute(text(f"DELETE FROM {table} WHERE plant_code = :p"), {"p": plant_code})
    for r in rows:
        names = [
            {"name": f["name"], "size_bytes": f.get("size_bytes", 0)} for f in json.loads(r.files)
        ]
        ctx.db.execute(
            text(
                "UPDATE imports SET status = 'deleted', files = :f, report = NULL, error = NULL, "
                "deleted_at = now(), deleted_by = :a WHERE import_id = :i"
            ),
            {"f": json.dumps(names), "a": ctx.principal.actor, "i": r.import_id},
        )
    audit(
        ctx.db,
        tenant,
        ctx.principal.actor,
        "plant_data_deleted",
        f"plant:{plant_code}",
        f"{len(rows)} imports and every row of the plant",
    )
    imports = settings.data_dir / str(tenant) / plant_code / "imports"
    for r in rows:  # once the delete is committed
        background.add_task(shutil.rmtree, imports / str(r.import_id), ignore_errors=True)
    return Response(status_code=204)
