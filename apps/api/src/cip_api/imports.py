"""Import page backend: upload exports, preview the column mapping, run the connector.

Files live under ``data_dir/<tenant>/<plant>/imports/<import_id>/`` (source/ and standard/).
The run happens in a worker (actor ``run_import``): connector -> standard layout -> load ->
data checklist -> plant data stored in the database. Personal columns never leave the reader.
"""

import contextlib
import json
import re
import shutil
import uuid
from collections.abc import Iterable
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
from cip_api.db.plant_store import replace_plant_data
from cip_api.errors import ApiProblem
from cip_api.facts import FactRunOut, fact_run, queue_facts, start_facts
from cip_api.jobs import enqueue
from cip_api.settings import Settings, get_settings
from cip_api.tenancy import Ctx, require
from cip_connectors.importer import import_export
from cip_connectors.mapping import MappingSet, load_mapping
from cip_connectors.privacy import personal_column_rule
from cip_connectors.readers import choose_delimiter, decode, find_source, inspect_file
from constraint_engine.io.plant_loader import REQUIRED, LoadedPlant, RowError, load_plant
from constraint_engine.quality.checklist import checklist, minimum_set, parse_requirements
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
    """An export of the minimum diagnostic set and whether this upload has it."""

    key: str
    sources: list[str]
    present: bool


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
    error: str | None
    """Technical reason, ``<step>:<ExceptionType>``; for IT, folded away on the page."""
    failed_step: FailedStep | None = None
    """Where a failed import stopped: read, load, check or store. The page explains each."""
    facts: FactRunOut | None = None
    """The numbers calculated from this import: calculating, ready or failed."""


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
    "orders": "orders",
    "routings": "routings",
    "products": "products",
    "events": "events",
    "calendar": "calendar",
}
"""Minimum diagnostic set (engine MINIMUM_SET keys) -> the standard table that must be filled."""


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


def _needed(files: list[FileCheckOut], mapping: MappingSet) -> list[NeededOut]:
    out = []
    for key, target in MINIMUM_TARGETS.items():
        sources = sorted({t.source for t in mapping.tables if t.target == target})
        if not sources:
            continue  # this export format does not carry it (e.g. no products, ADR-0009)
        present = any(f.readable and f.recognised_as in sources for f in files)
        out.append(NeededOut(key=key, sources=sources, present=present))
    return out


def _out(settings: Settings, tenant: uuid.UUID, row: Any, db: Connection) -> ImportOut:
    folder = import_dir(settings, tenant, row.plant_code, row.import_id) / "source"
    stored_files = json.loads(row.files)
    mapping = choose_mapping(f["name"] for f in stored_files)
    report = json.loads(row.report) if row.report else None
    files = [FileCheckOut.model_validate(f) for f in stored_files if "readable" in f]
    return ImportOut(
        import_id=row.import_id,
        plant_code=row.plant_code,
        status=row.status,
        created_at=row.created_at,
        files=files,
        expected_files=list(dict.fromkeys(t.source for t in mapping.tables)),
        needed=_needed(files, mapping),
        mapping=mapping.source_system,
        sources=preview(folder, mapping) if folder.exists() else [],
        report=report,
        minimum_set=[MinimumOut(**m) for m in (report or {}).get("minimum_set", [])],
        error=row.error,
        failed_step=_failed_step(row.error),
        facts=fact_run(db, row.import_id),
    )


COLUMNS = "import_id, plant_code, status, created_at, files, report, error"


def _row(db: Connection, import_id: uuid.UUID) -> Any:
    row = db.execute(
        text(f"SELECT {COLUMNS} FROM imports WHERE import_id = :i"), {"i": import_id}
    ).first()
    if row is None:
        raise ApiProblem("import_not_found")
    return row


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
            "INSERT INTO imports (tenant_id, plant_code, actor) VALUES (:t, :p, :a) "
            "RETURNING import_id"
        ),
        {"t": ctx.principal.tenant_id, "p": plant_code, "a": ctx.principal.actor},
    ).scalar_one()
    folder = import_dir(settings, ctx.principal.tenant_id, plant_code, import_id) / "source"
    folder.mkdir(parents=True, exist_ok=True)
    limit = settings.max_upload_mb * 1024 * 1024
    written = []
    for f in files:
        target = folder / str(f.filename)
        size = 0
        with target.open("wb") as out:
            while chunk := await f.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    shutil.rmtree(folder.parent, ignore_errors=True)
                    raise ApiProblem("file_too_large", limit_mb=settings.max_upload_mb)
                out.write(chunk)
        written.append(target)
    mapping = choose_mapping(p.name for p in written)
    stored = [check_file(p, mapping) for p in written]
    ctx.db.execute(
        text("UPDATE imports SET files = :f WHERE import_id = :i"),
        {"f": json.dumps(stored), "i": import_id},
    )
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


def run_import(settings: Settings, tenant: uuid.UUID, import_id: uuid.UUID) -> None:
    """The job: connector, load, checklist, store. Records 'done' or 'failed' (reason only)."""
    step: FailedStep = "read"
    try:
        with tenant_conn(settings, tenant) as conn:
            row = _row(conn, import_id)
            plant = conn.execute(
                text("SELECT plant_code, name, timezone_iana FROM plants WHERE plant_code = :p"),
                {"p": row.plant_code},
            ).one()
        folder = import_dir(settings, tenant, row.plant_code, import_id)
        mapping = choose_mapping(p.name for p in (folder / "source").iterdir())
        standard = folder / "standard"
        if standard.exists():
            shutil.rmtree(standard)
        report = import_export(folder / "source", mapping, standard, plant=dict(plant._mapping))
        step = "load"
        loaded = load_plant(standard, tenant_id=tenant)
        step = "check"
        items = checklist(parse_requirements(INPUT_DATA.read_text()), loaded)
        measured = task_times(pair_operations(loaded), per_product=False)
        # Rejected rows count against the standard file they would have filled (e.g. events.csv).
        target = {f"{t.source}.csv": f"{t.target}.csv" for t in mapping.tables}
        target |= {f"{t.source}.xlsx": f"{t.target}.csv" for t in mapping.tables}
        quality = quality_report(
            loaded,
            [RowError(target.get(e.file, e.file), e.line, e.reason) for e in report.row_errors],
        )
        step = "store"
        with tenant_conn(settings, tenant) as conn:
            stored = replace_plant_data(conn, tenant, row.plant_code, loaded)
            result = {
                "import": report.to_dict(),
                "load_errors": len(loaded.row_errors),
                "stored_rows": stored,
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
                "quality": quality_dict(quality, loaded),
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
            }
            conn.execute(
                text("UPDATE imports SET status = 'done', report = :r WHERE import_id = :i"),
                {"r": json.dumps(result, ensure_ascii=False), "i": import_id},
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
