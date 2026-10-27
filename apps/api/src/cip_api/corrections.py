"""Rows fixed in the app, next to the original (ADR-0010 point 7).

A correction sets one column of one line of an import's source file, or leaves the line out. The
file is never changed: the import is mapped again with its corrections, checked by the same rules
as any row, and the plant is rebuilt from the kept imports. Undoing a correction keeps it in the
list, with who undid it and when. Personal columns are dropped on read, so they can never be
shown or fixed here.
"""

import csv
import io
import json
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import Connection, text

from cip_api.ai import (
    AiExplanationOut,
    AiExplanationsOut,
    AiState,
    AiUnavailableError,
    OpenProblem,
    Provider,
    explain_problems,
    get_ai_provider,
)
from cip_api.auth.roles import Decision
from cip_api.auth.sessions import audit
from cip_api.db.plant_store import merge_imports, rebuild_plant_data, row_fixes
from cip_api.errors import ApiProblem
from cip_api.facts import Reason
from cip_api.imports import _ai, choose_mapping, import_dir, kept_imports, refresh_quality
from cip_api.refresh import refresh_after_change
from cip_api.settings import Settings, get_settings
from cip_api.tenancy import Ctx, require
from cip_connectors.excel import read_xlsx
from cip_connectors.importer import Fixes, ImportReport, import_export
from cip_connectors.mapping import MappingSet
from cip_connectors.privacy import personal_column_rule
from cip_connectors.readers import SourceTable, read_csv

router = APIRouter(tags=["corrections"])
View = Annotated[Ctx, Depends(require())]
Fix = Annotated[Ctx, Depends(require(page="import", decision=Decision.FIX_ROWS))]
NO_IMPORT = uuid.UUID(int=0)
"""No running import: the rebuild uses the kept imports as they are."""

COLUMNS = (
    "c.correction_id, c.plant_code, c.action, c.import_id, i.created_at AS import_created_at, "
    'c.file, c.line, c."column", c.original, c.value, c.target, c.target_key, c.event_at, '
    "c.reason, c.role, c.created_at, c.undone_at, c.undone_by, p.timezone_iana"
)
SELECT = (
    f"SELECT {COLUMNS} FROM corrections c LEFT JOIN imports i ON i.import_id = c.import_id "
    "JOIN plants p ON p.tenant_id = c.tenant_id AND p.plant_code = c.plant_code"
)


class CorrectionIn(BaseModel):
    """Fix one value of a source line, or leave the line out (``exclude``)."""

    file: str
    line: int = Field(ge=2, description="Line in the file; line 1 is the header.")
    column: str | None = None
    value: str | None = None
    exclude: bool = False
    reason: str


class CorrectionOut(BaseModel):
    correction_id: uuid.UUID
    plant_code: str
    action: Literal["set", "exclude", "remove"]
    import_id: uuid.UUID | None
    import_created_at: datetime | None
    file: str | None
    line: int | None
    column: str | None
    original: str | None
    value: str | None
    target: str | None
    target_key: list[str] | None
    event_at: datetime | None
    reason: str
    role: str
    created_at: datetime
    undone_at: datetime | None
    undone: bool
    """True once undone; it stays in the list."""
    timezone_iana: str
    """The plant's time zone, to show a removed calendar entry in plant local time."""


class RejectedRowOut(BaseModel):
    file: str
    line: int
    column: str | None
    value: str | None
    code: str | None
    """The import rule the value breaks (e.g. ``not_a_datetime``); None for older imports."""
    reason: str
    correction: CorrectionOut | None
    """The correction in use for this line, if any."""


class RejectedRowsOut(BaseModel):
    import_id: uuid.UUID
    total: int
    """Rejected rows of the import's run, in every file."""
    codes: dict[str, int]
    """Rejected rows per rule, for the filter."""
    fixed: int
    """Of those, fixed or left out in the app (corrections in use)."""
    shown: int
    """Rows matching the filter."""
    offset: int
    rows: list[RejectedRowOut]
    datetime_format: str
    """How the plant's export writes a date and time, e.g. ``20-07-2026 10:11``."""
    ai: AiState
    """``not_connected`` without a key: the page shows the standard explanations only."""
    ai_explanations: AiExplanationsOut | None
    """The AI's last explanations of this import's reasons, if asked."""


def _out(row: Any) -> CorrectionOut:
    data = dict(row._mapping)
    data["target_key"] = json.loads(row.target_key) if row.target_key else None
    data["undone"] = row.undone_at is not None
    data.pop("undone_by", None)
    return CorrectionOut.model_validate(data)


def corrections_of(db: Connection, plant_code: str) -> list[CorrectionOut]:
    rows = db.execute(
        text(f"{SELECT} WHERE c.plant_code = :p ORDER BY c.created_at DESC"), {"p": plant_code}
    )
    return [_out(r) for r in rows]


def _import(db: Connection, ctx: Ctx, import_id: uuid.UUID) -> Any:
    row = db.execute(
        text(
            "SELECT import_id, plant_code, status, report, created_at FROM imports "
            "WHERE import_id = :i"
        ),
        {"i": import_id},
    ).first()
    if row is None:
        raise ApiProblem("import_not_found")
    ctx.check_plant(row.plant_code)
    return row


def _read(path: Path, mapping: MappingSet) -> SourceTable:
    drop = personal_column_rule(mapping.personal_columns)
    if path.suffix == ".xlsx":
        return read_xlsx(path, drop)
    return read_csv(path, mapping.delimiter, drop)


def _example(mapping: MappingSet) -> str:
    return datetime(2026, 7, 20, 10, 11).strftime(mapping.datetime_format)


def _rule(code: str | None, mapping: MappingSet) -> str:
    """The import rule in plain words, for a fix that still breaks it."""
    return {
        "not_a_datetime": f"a date and time written like {_example(mapping)}",
        "not_a_number": "a number",
        "not_whole": "a whole number",
        "too_many_decimals": "an amount in euros with at most two decimals",
        "not_yes_no": "yes or no",
        "unknown_code": "a code the plant's export uses",
        "empty": "a value (the field cannot be empty)",
    }.get(code or "", "a value the import can read")


def rebuild_and_refresh(
    settings: Settings,
    ctx: Ctx,
    plant_code: str,
    background: BackgroundTasks,
    reason: Reason = "fix",
) -> None:
    """Rebuild the plant from its kept imports and corrections, then recalculate its numbers
    (after this request commits, so the calculation reads the rebuilt plant)."""
    tenant = ctx.principal.tenant_id
    merged = merge_imports(kept_imports(settings, ctx.db, tenant, plant_code, NO_IMPORT))
    rebuild_plant_data(ctx.db, tenant, plant_code, merged)
    refresh_quality(settings, ctx.db, tenant, plant_code)
    refresh_after_change(settings, ctx, plant_code, reason, background)


def _trial(folder: Path, mapping: MappingSet, fixes: Fixes) -> ImportReport:
    """Map the import with these fixes into a scratch folder: the same rules as the import."""
    with tempfile.TemporaryDirectory() as scratch:
        return import_export(folder / "source", mapping, Path(scratch), fixes=fixes)


@router.get("/imports/{import_id}/rejected-rows", response_model=RejectedRowsOut)
def rejected_rows(
    import_id: uuid.UUID,
    ctx: Annotated[Ctx, Depends(require(page="import"))],
    settings: Annotated[Settings, Depends(get_settings)],
    provider: Annotated[Provider | None, Depends(get_ai_provider)],
    code: str | None = None,
    file: str | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> RejectedRowsOut:
    """The rows the import's run rejected, with the rule, column and value, and their fixes."""
    row = _import(ctx.db, ctx, import_id)
    report = json.loads(row.report) if row.report else {}
    errors = (report.get("import") or {}).get("row_errors", [])
    folder = import_dir(settings, ctx.principal.tenant_id, row.plant_code, import_id) / "source"
    files = [p.name for p in folder.iterdir()] if folder.exists() else []
    mapping = choose_mapping(files)
    fixes = {
        (c.file, c.line): c
        for c in reversed(corrections_of(ctx.db, row.plant_code))
        if c.import_id == import_id and not c.undone and c.action != "remove"
    }
    codes: dict[str, int] = {}
    for e in errors:
        codes[e.get("code") or "other"] = codes.get(e.get("code") or "other", 0) + 1
    chosen = [
        e
        for e in errors
        if (code is None or (e.get("code") or "other") == code)
        and (file is None or e["file"] == file)
    ]
    return RejectedRowsOut(
        import_id=import_id,
        total=len(errors),
        codes=codes,
        fixed=sum(1 for e in errors if (e["file"], e["line"]) in fixes),
        shown=len(chosen),
        offset=offset,
        rows=[
            RejectedRowOut(
                file=e["file"],
                line=e["line"],
                column=e.get("column"),
                value=e.get("value"),
                code=e.get("code"),
                reason=e["reason"],
                correction=fixes.get((e["file"], e["line"])),
            )
            for e in chosen[offset : offset + limit]
        ],
        datetime_format=_example(mapping),
        ai="connected" if provider is not None else "not_connected",
        ai_explanations=report.get("ai_explanations"),
    )


@router.post("/imports/{import_id}/rejected-rows/explain", response_model=AiExplanationsOut)
def explain_rejected_rows(
    import_id: uuid.UUID,
    ctx: Fix,
    settings: Annotated[Settings, Depends(get_settings)],
    provider: Annotated[Provider | None, Depends(get_ai_provider)],
) -> AiExplanationsOut:
    """Ask the AI why the rows were rejected and how to fix the export (ADR-0011 §4). It gets
    the reason codes, file and column names and at most 5 anonymised values per reason; never
    personal columns, lines or counts. The answer is kept with the import, marked as the AI's."""
    row = _import(ctx.db, ctx, import_id)
    report = json.loads(row.report) if row.report else {}
    errors = (report.get("import") or {}).get("row_errors", [])
    if not errors:
        raise ApiProblem("nothing_to_explain")
    if provider is None:
        raise ApiProblem("ai_not_connected")
    folder = import_dir(settings, ctx.principal.tenant_id, row.plant_code, import_id) / "source"
    mapping = choose_mapping(p.name for p in folder.iterdir()) if folder.exists() else None
    personal = personal_column_rule(mapping.personal_columns if mapping else ())
    problems: dict[str, OpenProblem] = {}
    for e in errors:
        column = e.get("column")
        if column and personal(column):
            continue  # never sent; dropped on read, so this is only a guard
        code = e.get("code") or "other"
        p = problems.setdefault(
            code,
            OpenProblem(code, _rule(e.get("code"), mapping) if mapping else "", [], frozenset()),
        )
        if column and (e["file"], column) not in p.columns:
            p.columns.append((e["file"], column))
        if e.get("value"):
            p.values = p.values | {str(e["value"])}
    ai = _ai(ctx.db, settings, provider, import_id)
    before = ai.budget.spent_eur
    try:
        items = explain_problems(ai, list(problems.values()))
    except AiUnavailableError:
        items = []
    out = AiExplanationsOut(
        state=ai.state,
        items=[AiExplanationOut(**vars(i)) for i in items],
        asked_at=datetime.now(UTC),
    )
    earlier = float((report.get("ai_explanations") or {}).get("spent_eur", 0))
    report["ai_explanations"] = {
        **out.model_dump(mode="json"),
        "spent_eur": round(earlier + ai.budget.spent_eur - before, 4),
    }
    ctx.db.execute(
        text("UPDATE imports SET report = :r WHERE import_id = :i"),
        {"r": json.dumps(report, ensure_ascii=False), "i": import_id},
    )
    audit(
        ctx.db,
        ctx.principal.tenant_id,
        ctx.principal.actor,
        "import.explain",
        f"import:{import_id}",
        f"{row.plant_code}: AI {ai.state}, {len(items)} explanations",
    )
    return out


@router.post("/imports/{import_id}/corrections", response_model=CorrectionOut, status_code=201)
def make_correction(
    import_id: uuid.UUID,
    body: CorrectionIn,
    ctx: Fix,
    settings: Annotated[Settings, Depends(get_settings)],
    background: BackgroundTasks,
) -> CorrectionOut:
    """Fix a value or leave a line out; checked by the import's rules, then the plant rebuilds."""
    row = _import(ctx.db, ctx, import_id)
    if row.status != "done":
        raise ApiProblem("correction_needs_import_in_use")
    reason = body.reason.strip()
    if not reason:
        raise ApiProblem("correction_reason_required")
    tenant = ctx.principal.tenant_id
    folder = import_dir(settings, tenant, row.plant_code, import_id)
    path = folder / "source" / body.file
    if "/" in body.file or not path.is_file():
        raise ApiProblem("file_not_found")
    mapping = choose_mapping(p.name for p in (folder / "source").iterdir())
    source = _read(path, mapping)
    line = dict(source.rows).get(body.line)
    if line is None:
        raise ApiProblem("line_not_found", line=body.line, file=body.file)
    original = None
    if not body.exclude:
        column = body.column or ""
        if column in source.dropped_columns:
            raise ApiProblem("correction_personal_column")
        if column not in source.header:
            raise ApiProblem("correction_column_not_found", column=column, file=body.file)
        if body.value is None or not body.value.strip():
            raise ApiProblem("correction_value_required")
        original = None if line.get(column) is None else str(line.get(column))
    fixes = dict(row_fixes(ctx.db, [import_id]).get(import_id, {}))
    lines = dict(fixes.get(body.file, {}))
    if body.exclude:
        lines[body.line] = None
    else:
        lines[body.line] = {**(lines.get(body.line) or {}), str(body.column): str(body.value)}
    fixes[body.file] = lines
    trial = _trial(folder, mapping, fixes)
    still = [e for e in trial.row_errors if e.file == body.file and e.line == body.line]
    if still:
        raise ApiProblem("correction_still_rejected", rule=_rule(still[0].code, mapping))
    at = trial.fixed_at.get(body.file, {}).get(body.line)
    # One correction in use per line and column: a new one takes the place of the old one.
    replaced = ctx.db.execute(
        text(
            "UPDATE corrections SET undone_at = now(), undone_by = :a WHERE import_id = :i "
            "AND file = :f AND line = :l AND undone_at IS NULL AND (action = 'exclude' "
            'OR :x OR "column" = :c) RETURNING correction_id'
        ),
        {
            "a": ctx.principal.actor,
            "i": import_id,
            "f": body.file,
            "l": body.line,
            "x": body.exclude,
            "c": body.column,
        },
    ).all()
    new_id = ctx.db.execute(
        text(
            "INSERT INTO corrections (tenant_id, plant_code, action, import_id, file, line, "
            '"column", original, value, event_at, reason, actor, role) VALUES (:t, :p, :act, '
            ":i, :f, :l, :c, :o, :v, :at, :r, :a, :role) RETURNING correction_id"
        ),
        {
            "t": tenant,
            "p": row.plant_code,
            "act": "exclude" if body.exclude else "set",
            "i": import_id,
            "f": body.file,
            "l": body.line,
            "c": None if body.exclude else body.column,
            "o": original,
            "v": None if body.exclude else body.value,
            "at": datetime.fromisoformat(at.replace("Z", "+00:00")) if at else None,
            "r": reason,
            "a": ctx.principal.actor,
            "role": ctx.principal.role.value,
        },
    ).scalar_one()
    audit(
        ctx.db,
        tenant,
        ctx.principal.actor,
        "row_left_out" if body.exclude else "row_fixed",
        f"import:{import_id}",
        f"{body.file} line {body.line}" + (f", replaces {len(replaced)}" if replaced else ""),
    )
    rebuild_and_refresh(settings, ctx, row.plant_code, background)
    return _out(ctx.db.execute(text(f"{SELECT} WHERE c.correction_id = :c"), {"c": new_id}).one())


@router.delete("/corrections/{correction_id}", response_model=CorrectionOut)
def undo_correction(
    correction_id: uuid.UUID,
    ctx: Fix,
    settings: Annotated[Settings, Depends(get_settings)],
    background: BackgroundTasks,
) -> CorrectionOut:
    """Undo a correction: the original counts again; the correction stays in the list."""
    found = ctx.db.execute(
        text(f"{SELECT} WHERE c.correction_id = :c"), {"c": correction_id}
    ).first()
    if found is None:
        raise ApiProblem("correction_not_found")
    ctx.check_plant(found.plant_code)
    if found.undone_at is not None:
        raise ApiProblem("correction_already_undone")
    ctx.db.execute(
        text("UPDATE corrections SET undone_at = now(), undone_by = :a WHERE correction_id = :c"),
        {"a": ctx.principal.actor, "c": correction_id},
    )
    audit(
        ctx.db,
        ctx.principal.tenant_id,
        ctx.principal.actor,
        "correction_undone",
        f"correction:{correction_id}",
        f"{found.file or found.target} {found.line or ''}".strip(),
    )
    undone: Reason = (
        "fix"
        if found.action != "remove"
        else "calendar"
        if found.target == "calendar_windows"
        else "setup"
    )
    rebuild_and_refresh(settings, ctx, found.plant_code, background, undone)
    return _out(
        ctx.db.execute(text(f"{SELECT} WHERE c.correction_id = :c"), {"c": correction_id}).one()
    )


@router.get("/plants/{plant_code}/corrections", response_model=list[CorrectionOut])
def list_corrections(plant_code: str, ctx: View) -> list[CorrectionOut]:
    """Every correction of the plant, newest first; undone ones stay, marked undone."""
    ctx.check_plant(plant_code)
    return corrections_of(ctx.db, plant_code)


@router.get(
    "/plants/{plant_code}/corrections.csv",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}}},
)
def download_corrections(plant_code: str, ctx: View) -> Response:
    """The corrections as a CSV, to send back to the plant's ERP owner."""
    ctx.check_plant(plant_code)
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(
        [
            "file",
            "line",
            "column",
            "value_uploaded",
            "value_fixed",
            "action",
            "reason",
            "role",
            "fixed_at_utc",
            "undone_at_utc",
        ]
    )
    for c in reversed(corrections_of(ctx.db, plant_code)):
        writer.writerow(
            [
                c.file or c.target or "",
                c.line or (", ".join(c.target_key or [])),
                c.column or "",
                c.original or "",
                c.value or "",
                c.action,
                c.reason,
                c.role,
                c.created_at.astimezone(UTC).isoformat(),
                c.undone_at.astimezone(UTC).isoformat() if c.undone_at else "",
            ]
        )
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    return Response(
        out.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="corrections_{plant_code}_{stamp}.csv"'
        },
    )


def record_removal(
    ctx: Ctx, plant_code: str, target: str, key: list[str], reason: str | None
) -> None:
    """An imported row removed on Setup or Calendar: stored so a rebuild leaves it out."""
    why = (reason or "").strip()
    if not why:
        raise ApiProblem("removal_reason_required")
    ctx.db.execute(
        text(
            "INSERT INTO corrections (tenant_id, plant_code, action, target, target_key, reason, "
            "actor, role) VALUES (:t, :p, 'remove', :tg, :k, :r, :a, :role)"
        ),
        {
            "t": ctx.principal.tenant_id,
            "p": plant_code,
            "tg": target,
            "k": json.dumps(key),
            "r": why,
            "a": ctx.principal.actor,
            "role": ctx.principal.role.value,
        },
    )
