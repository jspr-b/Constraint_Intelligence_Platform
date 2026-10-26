"""Import page backend: upload exports, preview the column mapping, run the connector.

Files live under ``data_dir/<tenant>/<plant>/imports/<import_id>/`` (source/ and standard/).
The run happens in a worker (actor ``run_import``): connector -> standard layout -> the plant is
rebuilt from all kept imports (ADR-0010: events add, lists replace) -> data checklist on the whole
plant as stored. Personal columns never leave the reader.
"""

import contextlib
import json
import re
import shutil
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import asdict
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, UploadFile
from pydantic import BaseModel
from sqlalchemy import Connection, text

from cip_api.auth.roles import Decision
from cip_api.auth.sessions import audit, tenant_conn
from cip_api.db.plant_store import (
    TABLES,
    EventCounts,
    fixes_digest,
    load_plant_from_db,
    merge_imports,
    rebuild_plant_data,
    row_fixes,
)
from cip_api.errors import ApiProblem
from cip_api.facts import FactRunOut, fact_run, queue_facts, start_facts
from cip_api.jobs import enqueue
from cip_api.settings import Settings, get_settings
from cip_api.tenancy import Ctx, require
from cip_connectors.importer import Fixes, import_export
from cip_connectors.mapping import MappingSet, load_mapping
from cip_connectors.privacy import personal_column_rule
from cip_connectors.readers import choose_delimiter, decode, find_source, inspect_file
from constraint_engine.io.compare import compare_plants
from constraint_engine.io.plant_loader import REQUIRED, LoadedPlant, RowError, load_plant
from constraint_engine.quality.checklist import (
    OPTIONAL_SET,
    checklist,
    minimum_set,
    parse_requirements,
)
from constraint_engine.quality.report import QualityReport, event_period_weeks, quality_report
from constraint_engine.reconstruct.durations import pair_operations, task_times
from constraint_engine.summary import record_count

router = APIRouter(tags=["imports"])
REPO = Path(__file__).resolve().parents[4]
MAPPINGS = REPO / "packages" / "connectors" / "mappings"
GENERIC_MAPPING = MAPPINGS / "generic" / "mapping.yaml"
EXPORT_FORMATS = (GENERIC_MAPPING, MAPPINGS / "workshop_scans" / "mapping.yaml")
"""Export formats the Import page knows; the first one wins a tie."""
INPUT_DATA = REPO / "docs" / "input-data.md"
SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,100}\.(csv|xlsx)$")
View = Annotated[Ctx, Depends(require(page="import"))]
Run = Annotated[Ctx, Depends(require(page="import", decision=Decision.IMPORT_RUN_DIAGNOSTIC))]


def import_dir(settings: Settings, tenant: uuid.UUID, plant: str, import_id: uuid.UUID) -> Path:
    return settings.data_dir / str(tenant) / plant / "imports" / str(import_id)


class ColumnOut(BaseModel):
    name: str
    status: str
    """mapped, not_imported (personal data, dropped on read) or unused."""
    fields: list[str]
    example: str | None
    """First value in the file; never shown for personal columns."""
    conversions: list[str]
    """How the value is converted, e.g. ``code_table:resource`` or ``datetime``."""


class SourceOut(BaseModel):
    source: str
    targets: list[str]
    file: str | None
    columns: list[ColumnOut]
    missing_columns: list[str]
    """Columns the mapping reads that the file does not have."""
    readable: bool = True


class MinimumOut(BaseModel):
    key: str
    numbers: list[int]
    status: str


class FileCheckOut(BaseModel):
    """One uploaded file as inspected at upload: what it is and what is in it."""

    name: str
    size_bytes: int
    recognised_as: str | None
    """The export (mapping source) this file is, by name; None when no export has this name."""
    feeds: list[str]
    """Standard tables this file fills."""
    readable: bool
    problem: str | None
    """empty, no_header, not_text, single_column, unreadable_excel."""
    encoding: str | None
    delimiter: str | None
    columns: int
    header: list[str]
    personal_columns: list[str]
    rows: int
    preview: list[dict[str, str]]


class NeededOut(BaseModel):
    """An export of the minimum diagnostic set (or an optional one) and whether this upload has
    it."""

    key: str
    sources: list[str]
    present: bool
    minimum: bool = True
    """False for an export that adds euros, actions or confidence but is not needed to start."""
    in_plant: bool = False
    """The plant already has it (an earlier upload or the app); an upload without it keeps that."""


FailedStep = Literal["read", "load", "check", "store"]
FAILED_STEPS: tuple[FailedStep, ...] = ("read", "load", "check", "store")


def _failed_step(error: str | None) -> FailedStep | None:
    step = (error or "").split(":", 1)[0]
    return next((s for s in FAILED_STEPS if s == step), None)


class ImportOut(BaseModel):
    import_id: uuid.UUID
    plant_code: str
    status: str
    created_at: datetime
    files: list[FileCheckOut]
    expected_files: list[str]
    """Export names the mapping recognises (without .csv/.xlsx)."""
    needed: list[NeededOut]
    mapping: str
    sources: list[SourceOut]
    report: dict[str, Any] | None
    minimum_set: list[MinimumOut]
    optional_set: list[MinimumOut] = []
    """Exports that add euros, actions or confidence, with their status after the import."""
    error: str | None
    """Technical reason, ``<step>:<ExceptionType>``; for IT, folded away on the page."""
    failed_step: FailedStep | None = None
    """Where a failed import stopped: read, load, check or store. The page explains each."""
    facts: FactRunOut | None = None
    """The numbers calculated from this import: calculating, ready or failed."""
    by_role: str | None = None
    """The role of the account that uploaded it (never a name); ``system`` for jobs."""
    replaces: uuid.UUID | None = None
    """The import this one is a new version of (ADR-0010)."""
    replaced_by: uuid.UUID | None = None
    """The newer version that replaced this import, once it ran."""
    file_names: list[str] = []
    """The names of its files; for a deleted import the only thing kept of them."""
    deleted_at: datetime | None = None
    deleted_by_role: str | None = None
    """Who deleted it, as a role (never a name)."""


def _head(path: Path, mapping: MappingSet) -> tuple[list[str], dict[str, str]]:
    """Header and an example per column: the first non-empty value in the first 50 rows.
    Personal columns are dropped before any value is read."""
    personal = personal_column_rule(mapping.personal_columns)
    if path.suffix == ".xlsx":
        from cip_connectors.excel import read_xlsx

        table = read_xlsx(path, personal)
        examples: dict[str, str] = {}
        for _line, row in table.rows[:50]:
            for k, v in row.items():
                if k not in examples and v not in (None, ""):
                    examples[k] = str(v)
        return table.header + table.dropped_columns, examples
    import csv
    import io

    text_, _encoding = decode(path.read_bytes())
    delimiter = choose_delimiter(text_.split("\n", 1)[0], mapping.delimiter)
    reader = csv.reader(io.StringIO(text_, newline=""), delimiter=delimiter)
    header = [c.strip() for c in next(reader, [])]
    keep = [(i, h) for i, h in enumerate(header) if not personal(h)]
    found: dict[str, str] = {}
    for _n, values in zip(range(50), reader, strict=False):
        for i, h in keep:
            if h not in found and i < len(values) and values[i].strip():
                found[h] = values[i].strip()
    return header, found


def preview(source_dir: Path, mapping: MappingSet) -> list[SourceOut]:
    """For each source the mapping reads: which file, and what happens to each column."""
    personal = personal_column_rule(mapping.personal_columns)
    out = []
    for source in dict.fromkeys(t.source for t in mapping.tables):
        tables = [t for t in mapping.tables if t.source == source]
        reads: dict[str, list[str]] = {}
        conversions: dict[str, list[str]] = {}
        for t in tables:
            for field_name, rule in t.fields.items():
                if rule.from_:
                    reads.setdefault(rule.from_, []).append(f"{t.target}.{field_name}")
                    how = conversions.setdefault(rule.from_, [])
                    if rule.code_table and f"code_table:{rule.code_table}" not in how:
                        how.append(f"code_table:{rule.code_table}")
                    if rule.type != "str" and rule.type not in how:
                        how.append(rule.type)
        path = find_source(source_dir, source)
        readable = True
        try:
            header, first = _head(path, mapping) if path else ([], {})
        except Exception:  # a corrupt or password-protected file: say so, never guess
            header, first, readable = [], {}, False
        columns = [
            ColumnOut(
                name=c,
                status="not_imported" if personal(c) else "mapped" if c in reads else "unused",
                fields=[] if personal(c) else reads.get(c, []),
                example=None if personal(c) else first.get(c),
                conversions=[] if personal(c) else conversions.get(c, []),
            )
            for c in header
        ]
        out.append(
            SourceOut(
                source=source,
                targets=sorted({t.target for t in tables}),
                file=path.name if path else None,
                columns=columns,
                missing_columns=[c for c in reads if path and readable and c not in header],
                readable=readable,
            )
        )
    return out


MINIMUM_TARGETS = {
    "events": "events",
    "steps": "resources",
    "shifts": "calendar",
}
"""Minimum diagnostic set (engine MINIMUM_SET keys) -> the standard table that must be filled."""

OPTIONAL_TARGETS = {
    "orders": "orders",
    "products": "products",
    "routings": "routings",
    "teams": "teams",
}
"""Optional exports (engine OPTIONAL_SET keys that come from their own file) -> standard table."""


@lru_cache
def _formats() -> tuple[MappingSet, ...]:
    return tuple(load_mapping(p) for p in EXPORT_FORMATS)


def choose_mapping(file_names: Iterable[str]) -> MappingSet:
    """The export format whose file names match the most uploaded files (ADR-0009: a plant
    sends its own format; we never guess columns, we recognise a known format by its files)."""
    stems = {Path(n).stem.lower() for n in file_names}
    return max(_formats(), key=lambda m: len(stems & {t.source.lower() for t in m.tables}))


def check_file(path: Path, mapping: MappingSet) -> dict[str, Any]:
    """Inspect an uploaded file once (stored with the import); personal values are never read."""
    sources = {t.source.lower(): t.source for t in mapping.tables}
    source = sources.get(path.stem.lower())
    info = inspect_file(path, mapping.delimiter, personal_column_rule(mapping.personal_columns))
    return {
        "name": path.name,
        "size_bytes": path.stat().st_size,
        "recognised_as": source,
        "feeds": sorted({t.target for t in mapping.tables if t.source == source}),
        "readable": info.readable,
        "problem": info.problem,
        "encoding": info.encoding,
        "delimiter": info.delimiter,
        "columns": len(info.header),
        "header": info.header,
        "personal_columns": info.personal_columns,
        "rows": info.rows,
        "preview": info.preview,
    }


def _needed(
    files: list[FileCheckOut], mapping: MappingSet, plant: tuple[Connection, str] | None = None
) -> list[NeededOut]:
    """Which exports this upload has; with ``plant``, also which the plant already has, so a
    later upload with only some files does not show the others as missing (ADR-0010)."""
    out = []
    for minimum, targets in ((True, MINIMUM_TARGETS), (False, OPTIONAL_TARGETS)):
        for key, target in targets.items():
            sources = sorted({t.source for t in mapping.tables if t.target == target})
            if not sources:
                continue  # this export format does not carry it (e.g. no products, ADR-0009)
            present = any(f.readable and f.recognised_as in sources for f in files)
            in_plant = False
            if plant and not present:
                db, plant_code = plant
                in_plant = bool(
                    db.execute(
                        text(
                            f"SELECT EXISTS (SELECT 1 FROM {TABLES[target]} WHERE plant_code = :p)"
                        ),
                        {"p": plant_code},
                    ).scalar_one()
                )
            out.append(
                NeededOut(
                    key=key, sources=sources, present=present, minimum=minimum, in_plant=in_plant
                )
            )
    return out


def _out(settings: Settings, tenant: uuid.UUID, row: Any, db: Connection) -> ImportOut:
    folder = import_dir(settings, tenant, row.plant_code, row.import_id) / "source"
    stored_files = json.loads(row.files)
    mapping = choose_mapping(f["name"] for f in stored_files)
    report = json.loads(row.report) if row.report else None
    files = [FileCheckOut.model_validate(f) for f in stored_files if "readable" in f]
    by_role = _role_of(db, row.actor)
    replaced_by = db.execute(
        text("SELECT import_id FROM imports WHERE replaces = :i AND status = 'done'"),
        {"i": row.import_id},
    ).scalar_one_or_none()
    return ImportOut(
        by_role=by_role,
        replaces=row.replaces,
        replaced_by=replaced_by,
        import_id=row.import_id,
        plant_code=row.plant_code,
        status=row.status,
        created_at=row.created_at,
        files=files,
        expected_files=list(dict.fromkeys(t.source for t in mapping.tables)),
        needed=_needed(files, mapping, (db, row.plant_code) if row.status == "uploaded" else None),
        mapping=mapping.source_system,
        sources=preview(folder, mapping) if folder.exists() else [],
        report=report,
        minimum_set=[MinimumOut(**m) for m in (report or {}).get("minimum_set", [])],
        optional_set=[MinimumOut(**m) for m in (report or {}).get("optional_set", [])],
        error=row.error,
        failed_step=_failed_step(row.error),
        facts=fact_run(db, row.import_id),
        file_names=[f["name"] for f in stored_files],
        deleted_at=row.deleted_at,
        deleted_by_role=_role_of(db, row.deleted_by) if row.deleted_by else None,
    )


def _role_of(db: Connection, actor: str) -> str | None:
    """The role of an actor (``user:<id>``), never a name; ``system`` for jobs."""
    if str(actor).startswith("user:"):
        with contextlib.suppress(ValueError):
            role: str | None = db.execute(
                text("SELECT role FROM users WHERE user_id = :u"),
                {"u": uuid.UUID(str(actor).removeprefix("user:"))},
            ).scalar_one_or_none()
            return role
        return None
    return "system" if str(actor).startswith("system") else None


COLUMNS = (
    "import_id, plant_code, status, created_at, files, report, error, actor, replaces, "
    "deleted_at, deleted_by"
)


def _row(db: Connection, import_id: uuid.UUID) -> Any:
    row = db.execute(
        text(f"SELECT {COLUMNS} FROM imports WHERE import_id = :i"), {"i": import_id}
    ).first()
    if row is None:
        raise ApiProblem("import_not_found")
    return row


async def _save(folder: Path, files: list[UploadFile], settings: Settings) -> list[Path]:
    """Write uploaded files into an import's source folder, with the size limit."""
    for f in files:
        if not f.filename or not SAFE_NAME.fullmatch(f.filename):
            raise ApiProblem("bad_file_name")
    folder.mkdir(parents=True, exist_ok=True)
    limit = settings.max_upload_mb * 1024 * 1024
    written = []
    for f in files:
        target = folder / str(f.filename)
        part = target.with_suffix(target.suffix + ".part")
        size = 0
        with part.open("wb") as out:
            while chunk := await f.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    out.close()
                    part.unlink(missing_ok=True)
                    raise ApiProblem("file_too_large", limit_mb=settings.max_upload_mb)
                out.write(chunk)
        part.replace(target)
        written.append(target)
    return written


def _check_folder(db: Connection, folder: Path, import_id: uuid.UUID) -> list[dict[str, Any]]:
    """Run the file check on every file in the source folder and store the result."""
    present = sorted(p for p in folder.iterdir() if p.is_file() and not p.name.endswith(".part"))
    mapping = choose_mapping(p.name for p in present)
    stored = [check_file(p, mapping) for p in present]
    db.execute(
        text("UPDATE imports SET files = :f WHERE import_id = :i"),
        {"f": json.dumps(stored), "i": import_id},
    )
    return stored


@router.post("/plants/{plant_code}/imports", response_model=ImportOut, status_code=201)
async def upload(
    plant_code: str,
    files: list[UploadFile],
    ctx: Run,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ImportOut:
    """Store uploaded CSV/Excel exports for a plant. Nothing is read into the platform yet."""
    ctx.check_plant(plant_code)
    if (
        ctx.db.execute(
            text("SELECT 1 FROM plants WHERE plant_code = :p"), {"p": plant_code}
        ).first()
        is None
    ):
        raise ApiProblem("plant_not_found")
    if not files:
        raise ApiProblem("no_files")
    for f in files:
        if not f.filename or not SAFE_NAME.fullmatch(f.filename):
            raise ApiProblem("bad_file_name")
    import_id = ctx.db.execute(
        text(
            "INSERT INTO imports (tenant_id, plant_code, actor, slot_at) "
            "VALUES (:t, :p, :a, now()) RETURNING import_id"
        ),
        {"t": ctx.principal.tenant_id, "p": plant_code, "a": ctx.principal.actor},
    ).scalar_one()
    folder = import_dir(settings, ctx.principal.tenant_id, plant_code, import_id) / "source"
    try:
        await _save(folder, files, settings)
    except ApiProblem:
        shutil.rmtree(folder.parent, ignore_errors=True)
        raise
    stored = _check_folder(ctx.db, folder, import_id)
    audit(
        ctx.db,
        ctx.principal.tenant_id,
        ctx.principal.actor,
        "import_uploaded",
        f"import:{import_id}",
        f"{plant_code}: {len(stored)} files",
    )
    return _out(settings, ctx.principal.tenant_id, _row(ctx.db, import_id), ctx.db)


@router.get("/plants/{plant_code}/imports", response_model=list[ImportOut])
def list_imports(
    plant_code: str, ctx: View, settings: Annotated[Settings, Depends(get_settings)]
) -> list[ImportOut]:
    ctx.check_plant(plant_code)
    rows = ctx.db.execute(
        text(
            f"SELECT {COLUMNS} FROM imports WHERE plant_code = :p ORDER BY created_at DESC LIMIT 20"
        ),
        {"p": plant_code},
    )
    return [_out(settings, ctx.principal.tenant_id, r, ctx.db) for r in rows]


@router.get("/imports/{import_id}", response_model=ImportOut)
def get_import(
    import_id: uuid.UUID, ctx: View, settings: Annotated[Settings, Depends(get_settings)]
) -> ImportOut:
    row = _row(ctx.db, import_id)
    ctx.check_plant(row.plant_code)
    return _out(settings, ctx.principal.tenant_id, row, ctx.db)


@router.post("/imports/{import_id}/run", response_model=ImportOut, status_code=202)
def run(
    import_id: uuid.UUID,
    ctx: Run,
    settings: Annotated[Settings, Depends(get_settings)],
    background: BackgroundTasks,
) -> ImportOut:
    """Start the connector in a worker. The page polls this import until it is done or failed."""
    row = _row(ctx.db, import_id)
    ctx.check_plant(row.plant_code)
    busy = ctx.db.execute(
        text(
            "SELECT 1 FROM imports WHERE plant_code = :p AND status = 'running' UNION ALL "
            "SELECT 1 FROM fact_runs WHERE plant_code = :p AND status = 'calculating' "
            "AND started_at > now() - interval '15 minutes'"
        ),
        {"p": row.plant_code},
    ).first()
    if busy:
        raise ApiProblem("import_running")
    # Committed at once in its own transaction, so the job never waits on this request.
    with tenant_conn(settings, ctx.principal.tenant_id) as conn:
        conn.execute(
            text("UPDATE imports SET status = 'running', error = NULL WHERE import_id = :i"),
            {"i": import_id},
        )
    audit(
        ctx.db,
        ctx.principal.tenant_id,
        ctx.principal.actor,
        "import_started",
        f"import:{import_id}",
    )
    tenant = ctx.principal.tenant_id
    if settings.run_jobs_inline:
        background.add_task(_run_quietly, settings, tenant, import_id)
    else:
        enqueue("run_import", str(tenant), str(import_id))
    return _out(settings, tenant, _row(ctx.db, import_id), ctx.db)


# --- Change an import's files (ADR-0010 point 8) -----------------------------------------


def _changeable(db: Connection, import_id: uuid.UUID, ctx: Ctx) -> Any:
    row = _row(db, import_id)
    ctx.check_plant(row.plant_code)
    if row.status == "running":
        raise ApiProblem("import_running")
    if row.status in ("replaced", "deleted"):
        raise ApiProblem("import_not_changeable")
    return row


def _new_version(settings: Settings, ctx: Ctx, row: Any) -> tuple[uuid.UUID, Path]:
    """A copy of an import that already ran: the change goes into this new version."""
    tenant = ctx.principal.tenant_id
    new_id = ctx.db.execute(
        text(
            "INSERT INTO imports (tenant_id, plant_code, actor, replaces, slot_at) "
            "SELECT tenant_id, plant_code, :a, import_id, coalesce(slot_at, created_at) "
            "FROM imports WHERE import_id = :i RETURNING import_id"
        ),
        {"a": ctx.principal.actor, "i": row.import_id},
    ).scalar_one()
    old = import_dir(settings, tenant, row.plant_code, row.import_id) / "source"
    new = import_dir(settings, tenant, row.plant_code, new_id) / "source"
    shutil.copytree(old, new)
    return new_id, new


@router.post("/imports/{import_id}/files", response_model=ImportOut)
async def change_files(
    import_id: uuid.UUID,
    files: list[UploadFile],
    ctx: Run,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ImportOut:
    """Add or replace files. Before the run the upload changes; after it, a new version."""
    row = _changeable(ctx.db, import_id, ctx)
    if not files:
        raise ApiProblem("no_files")
    target, folder = (
        row.import_id,
        (import_dir(settings, ctx.principal.tenant_id, row.plant_code, row.import_id) / "source"),
    )
    if row.status == "done":
        target, folder = _new_version(settings, ctx, row)
    try:
        written = await _save(folder, files, settings)
    except ApiProblem:
        if target != row.import_id:
            shutil.rmtree(folder.parent, ignore_errors=True)
        raise
    _check_folder(ctx.db, folder, target)
    for f in written:
        audit(
            ctx.db,
            ctx.principal.tenant_id,
            ctx.principal.actor,
            "import_file_added",
            f"import:{target}",
            f"{row.plant_code}: {f.name}",
        )
    return _out(settings, ctx.principal.tenant_id, _row(ctx.db, target), ctx.db)


@router.delete("/imports/{import_id}/files/{name}", response_model=ImportOut)
def remove_file(
    import_id: uuid.UUID,
    name: str,
    ctx: Run,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ImportOut:
    """Remove a file. Before the run the upload changes; after it, a new version."""
    row = _changeable(ctx.db, import_id, ctx)
    folder = import_dir(settings, ctx.principal.tenant_id, row.plant_code, row.import_id) / "source"
    if not SAFE_NAME.fullmatch(name) or not (folder / name).is_file():
        raise ApiProblem("file_not_found")
    if sum(1 for p in folder.iterdir() if p.is_file()) <= 1:
        raise ApiProblem("last_file")
    target = row.import_id
    if row.status == "done":
        target, folder = _new_version(settings, ctx, row)
    (folder / name).unlink()
    _check_folder(ctx.db, folder, target)
    audit(
        ctx.db,
        ctx.principal.tenant_id,
        ctx.principal.actor,
        "import_file_removed",
        f"import:{target}",
        f"{row.plant_code}: {name}",
    )
    return _out(settings, ctx.principal.tenant_id, _row(ctx.db, target), ctx.db)


# --- See what an upload changes before running it -----------------------------------------


class ListChangeOut(BaseModel):
    name: str
    before: int
    after: int
    new: list[str]
    gone: list[str]


class PreviewWarningOut(BaseModel):
    code: Literal["steps_removed_with_events", "events_removed", "period_shrinks"]
    items: list[str]
    count: int


class PreviewOut(BaseModel):
    """The plant now against the plant after this upload, from the engine (ADR-0010)."""

    events_before: int
    events_after: int
    events_added: int
    events_removed: int
    period_before: tuple[datetime | None, datetime | None]
    period_after: tuple[datetime | None, datetime | None]
    lists: list[ListChangeOut]
    warnings: list[PreviewWarningOut]


@router.get("/imports/{import_id}/preview", response_model=PreviewOut)
def what_changes(
    import_id: uuid.UUID, ctx: View, settings: Annotated[Settings, Depends(get_settings)]
) -> PreviewOut:
    """Rebuild the plant with this upload in a transaction that is rolled back, and compare."""
    row = _row(ctx.db, import_id)
    ctx.check_plant(row.plant_code)
    if row.status != "uploaded":
        raise ApiProblem("preview_after_run")
    tenant = ctx.principal.tenant_id
    plant = ctx.db.execute(
        text("SELECT plant_code, name, timezone_iana FROM plants WHERE plant_code = :p"),
        {"p": row.plant_code},
    ).one()
    folder = import_dir(settings, tenant, row.plant_code, import_id)
    if not any((folder / "source").iterdir()):
        raise ApiProblem("no_files")
    map_import(folder, dict(plant._mapping))
    before = load_plant_from_db(ctx.db, tenant, row.plant_code)
    trial = ctx.db.begin_nested()
    try:
        merged = merge_imports(kept_imports(settings, ctx.db, tenant, row.plant_code, import_id))
        rebuild_plant_data(ctx.db, tenant, row.plant_code, merged)
        after = load_plant_from_db(ctx.db, tenant, row.plant_code)
    finally:
        trial.rollback()
    p = compare_plants(before, after)
    return PreviewOut(
        events_before=p.events_before,
        events_after=p.events_after,
        events_added=p.events_added,
        events_removed=p.events_removed,
        period_before=p.period_before,
        period_after=p.period_after,
        lists=[
            ListChangeOut(
                name=c.name, before=c.before, after=c.after, new=list(c.new), gone=list(c.gone)
            )
            for c in p.lists
        ],
        warnings=[
            PreviewWarningOut(code=w.code, items=list(w.items), count=w.count)  # type: ignore[arg-type]
            for w in p.warnings
        ],
    )


# --- Which imports the data in use comes from ---------------------------------------------


class InUseOut(BaseModel):
    """Per import in use: how many events it brought and which lists come from it."""

    import_id: uuid.UUID
    created_at: datetime
    events: int
    lists: list[str]


@router.get("/plants/{plant_code}/data-in-use", response_model=list[InUseOut])
def data_in_use(plant_code: str, ctx: View) -> list[InUseOut]:
    ctx.check_plant(plant_code)
    events: dict[uuid.UUID, int] = {
        i: n
        for i, n in ctx.db.execute(
            text(
                "SELECT import_id, count(*) FROM operation_events WHERE plant_code = :p "
                "AND import_id IS NOT NULL GROUP BY import_id"
            ),
            {"p": plant_code},
        )
    }
    lists: dict[uuid.UUID, list[str]] = {}
    for name, table in TABLES.items():
        if name == "events":
            continue
        for (i,) in ctx.db.execute(
            text(
                f"SELECT DISTINCT import_id FROM {table} "
                "WHERE plant_code = :p AND import_id IS NOT NULL"
            ),
            {"p": plant_code},
        ):
            lists.setdefault(i, []).append(name)
    rows = ctx.db.execute(
        text(
            "SELECT import_id, created_at FROM imports WHERE plant_code = :p AND status = 'done' "
            "ORDER BY coalesce(slot_at, created_at), created_at"
        ),
        {"p": plant_code},
    )
    return [
        InUseOut(
            import_id=r.import_id,
            created_at=r.created_at,
            events=events.get(r.import_id, 0),
            lists=sorted(lists.get(r.import_id, [])),
        )
        for r in rows
        if r.import_id in events or r.import_id in lists
    ]


def quality_section(
    mapping: MappingSet, plant: LoadedPlant, issues: Iterable[dict[str, Any]], fixes: Fixes
) -> dict[str, Any]:
    """The quality report of an import as stored: the rows its run rejected that are not fixed
    or left out in the app, and per file how many were (ADR-0010).

    Rejected rows count against the standard file they would fill (e.g. events.csv) and are
    grouped by the rule's code where there is one, so the page can name the rule in plain words.
    """
    target = {f"{t.source}.csv": f"{t.target}.csv" for t in mapping.tables}
    target |= {f"{t.source}.xlsx": f"{t.target}.csv" for t in mapping.tables}
    fixed = {(file, line) for file, lines in fixes.items() for line in lines}
    errors = [
        RowError(
            target.get(e["file"], e["file"]),
            e["line"],
            f"{e['code']}: {e['reason']}" if e.get("code") else e["reason"],
        )
        for e in issues
        if (e["file"], e["line"]) not in fixed
    ]
    out = quality_dict(quality_report(plant, errors), plant)
    per_file: dict[str, int] = {}
    for file, _ in fixed:
        per_file[target.get(file, file)] = per_file.get(target.get(file, file), 0) + 1
    for f in out["files"]:
        f["fixed"] = per_file.get(f["file"], 0)
    return out


def refresh_quality(settings: Settings, conn: Connection, tenant: uuid.UUID, plant: str) -> None:
    """After a fix, an undo or a removal: the latest import's quality report from the rebuilt
    plant, so Data quality counts the rows still rejected and the ones fixed in the app."""
    row = conn.execute(
        text(
            "SELECT import_id, report FROM imports WHERE plant_code = :p AND status = 'done' "
            "ORDER BY created_at DESC LIMIT 1"
        ),
        {"p": plant},
    ).first()
    if row is None or not row.report:
        return
    report = json.loads(row.report)
    if "quality" not in report:
        return
    folder = import_dir(settings, tenant, plant, row.import_id) / "source"
    mapping = choose_mapping(p.name for p in folder.iterdir())
    fixes = row_fixes(conn, [row.import_id]).get(row.import_id) or {}
    loaded = load_plant_from_db(conn, tenant, plant)
    issues = (report.get("import") or {}).get("row_errors", [])
    report["quality"] = quality_section(mapping, loaded, issues, fixes)
    conn.execute(
        text("UPDATE imports SET report = :r WHERE import_id = :i"),
        {"r": json.dumps(report, ensure_ascii=False), "i": row.import_id},
    )


def quality_dict(q: QualityReport, plant: LoadedPlant) -> dict[str, Any]:
    """The engine's quality report as stored JSON: every number a Figure or a plain count."""
    times = [e.at for e in plant.events]
    return {
        "score": q.score.to_dict(),
        "rows": record_count("all", sum(f.rows for f in q.files), len(q.rejected_rows)).to_dict(),
        "files": [
            {
                "file": f.file,
                "rows": f.rows,
                "rejected": f.rejected,
                "reasons": f.reasons,
                "examples": [{"line": e.line, "reason": e.reason} for e in f.examples[:5]],
            }
            for f in q.files
        ],
        "files_required": len(REQUIRED),
        "files_missing": sorted(n for n in plant.missing_files if n in REQUIRED),
        "gaps": [
            {
                "code": g.code,
                "description": g.description,
                "confidence_impact": g.confidence_impact.label,
                "fix": g.fix,
                "resource_code": g.resource_code,
                "count": g.count,
            }
            for g in q.gaps
        ],
        "event_period_weeks": event_period_weeks(plant.events).to_dict(),
        "event_period_start_at": min(times).isoformat() if times else None,
        "event_period_end_at": max(times).isoformat() if times else None,
    }


def _run_quietly(settings: Settings, tenant: uuid.UUID, import_id: uuid.UUID) -> None:
    with contextlib.suppress(Exception):  # the failure is recorded on the import
        run_import(settings, tenant, import_id)


ID_RULE = ".ids-content-v1"
"""Marker in standard/: event ids made from the event itself (ADR-0010). Older folders are
mapped again from their source files, which never change."""


def map_import(folder: Path, plant: dict[str, Any], fixes: Fixes | None = None) -> Any:
    """Map an import's source files, with the rows fixed in the app, to its standard layout.

    Returns the connector report. The marker holds the stamp of the fixes it was mapped with.
    """
    mapping = choose_mapping(p.name for p in (folder / "source").iterdir())
    standard = folder / "standard"
    if standard.exists():
        shutil.rmtree(standard)
    report = import_export(folder / "source", mapping, standard, plant=plant, fixes=fixes)
    (standard / ID_RULE).write_text(fixes_digest(fixes))
    return report


def _mapped_with(folder: Path) -> str | None:
    marker = folder / "standard" / ID_RULE
    return marker.read_text() if marker.exists() else None


def kept_imports(
    settings: Settings, conn: Connection, tenant: uuid.UUID, plant_code: str, running: uuid.UUID
) -> list[tuple[uuid.UUID, LoadedPlant]]:
    """The plant's kept imports in upload order, each as its standard layout (ADR-0010)."""
    plant = conn.execute(
        text("SELECT plant_code, name, timezone_iana FROM plants WHERE plant_code = :p"),
        {"p": plant_code},
    ).one()
    # The running import takes the place of the version it replaces (ADR-0010).
    ids: Sequence[uuid.UUID] = (
        conn.execute(
            text(
                "SELECT import_id FROM imports WHERE plant_code = :p "
                "AND (status = 'done' OR import_id = :i) "
                "AND import_id IS DISTINCT FROM "
                "(SELECT replaces FROM imports WHERE import_id = :i) "
                "ORDER BY coalesce(slot_at, created_at), created_at, import_id"
            ),
            {"p": plant_code, "i": running},
        )
        .scalars()
        .all()
    )
    fixes = row_fixes(conn, ids)
    out = []
    for i in ids:
        folder = import_dir(settings, tenant, plant_code, i)
        if _mapped_with(folder) != fixes_digest(fixes.get(i)):  # new id rule or other fixes
            map_import(folder, dict(plant._mapping), fixes.get(i))
        out.append((i, load_plant(folder / "standard", tenant_id=tenant)))
    return out


def _period(start: datetime | None, end: datetime | None) -> dict[str, str | None]:
    return {
        "start_at": start.isoformat() if start else None,
        "end_at": end.isoformat() if end else None,
    }


def run_import(settings: Settings, tenant: uuid.UUID, import_id: uuid.UUID) -> None:
    """The job: connector, rebuild from kept imports, checklist, store. Records 'done' or 'failed'.

    A failure leaves the plant's previous data in use (one transaction) and records the step.
    """
    step: FailedStep = "read"
    try:
        with tenant_conn(settings, tenant) as conn:
            row = _row(conn, import_id)
            plant = conn.execute(
                text("SELECT plant_code, name, timezone_iana FROM plants WHERE plant_code = :p"),
                {"p": row.plant_code},
            ).one()
            fixes = row_fixes(conn, [import_id]).get(import_id)
        folder = import_dir(settings, tenant, row.plant_code, import_id)
        mapping = choose_mapping(p.name for p in (folder / "source").iterdir())
        report = map_import(folder, dict(plant._mapping), fixes)
        step = "load"
        own = load_plant(folder / "standard", tenant_id=tenant)
        step = "store"
        with tenant_conn(settings, tenant) as conn:
            merged = merge_imports(kept_imports(settings, conn, tenant, row.plant_code, import_id))
            stored = rebuild_plant_data(conn, tenant, row.plant_code, merged)
            loaded = load_plant_from_db(conn, tenant, row.plant_code)
            step = "check"
            loaded.row_errors.extend(own.row_errors)
            items = checklist(parse_requirements(INPUT_DATA.read_text()), loaded)
            measured = task_times(pair_operations(loaded), per_product=False)
            quality = quality_section(
                mapping, loaded, [vars(e) for e in report.row_errors], fixes or {}
            )
            counts = merged.events.get(import_id, EventCounts())
            ats = [e.at for e in loaded.events]
            events = {
                "added": counts.added,
                "already_there": counts.already_there,
                "changed": counts.changed,
                "repeated_in_file": counts.repeated_in_file,
                "in_plant": len(loaded.events),
                "period_added": _period(counts.period_start_at, counts.period_end_at),
                "plant_period": _period(min(ats, default=None), max(ats, default=None)),
            }
            replaced = sorted(k for k, v in merged.lists_from.items() if v == import_id)
            result = {
                "import": report.to_dict(),
                "events": events,
                "lists_replaced": replaced,
                "load_errors": len(loaded.row_errors),
                "stored_rows": {k: v for k, v in stored.items() if v},
                "checklist": [
                    {
                        "number": i.requirement.number,
                        "data": i.requirement.data,
                        "need": i.requirement.level,
                        "status": i.status,
                        "detail": i.detail,
                    }
                    for i in items
                ],
                "quality": quality,
                "task_times": [
                    {
                        "resource_code": m.resource_code,
                        "operation": m.operation,
                        "median_min_per_unit": m.median_min_per_unit.to_dict(),
                    }
                    for m in measured
                ],
                "minimum_set": [
                    {**asdict(m), "numbers": list(m.numbers)} for m in minimum_set(items)
                ],
                "optional_set": [
                    {**asdict(m), "numbers": list(m.numbers)}
                    for m in minimum_set(items, OPTIONAL_SET)
                ],
            }
            conn.execute(
                text("UPDATE imports SET status = 'done', report = :r WHERE import_id = :i"),
                {"r": json.dumps(result, ensure_ascii=False), "i": import_id},
            )
            if row.replaces:  # the older version stays in the history, no longer in use
                conn.execute(
                    text("UPDATE imports SET status = 'replaced' WHERE import_id = :o"),
                    {"o": row.replaces},
                )
            audit(
                conn,
                tenant,
                "system:import",
                "import_done",
                f"import:{import_id}",
                f"{sum(stored.values())} rows stored",
            )
            start_facts(conn, tenant, row.plant_code, import_id)
    except Exception as exc:  # recorded for the page; values from the files never appear here
        with tenant_conn(settings, tenant) as conn:
            conn.execute(
                text("UPDATE imports SET status = 'failed', error = :e WHERE import_id = :i"),
                {"e": f"{step}:{type(exc).__name__}", "i": import_id},
            )
        raise
    queue_facts(settings, tenant, import_id)
