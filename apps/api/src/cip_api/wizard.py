"""Mapping wizard, step 1 (ADR-0011 §2): take the whole export as it comes and say what each
table is and how the tables link. The client names or skips a table the app cannot place.

The recognition is stored with the import (``imports.wizard``), with the client's answers, so
the page shows it without reading the files again.
"""

import re
import zipfile
from pathlib import Path
from typing import Any, Literal

from fastapi import UploadFile
from pydantic import BaseModel

from cip_api.ai import Ai, AiState, AiUnavailableError, OpenColumn, suggest_columns
from cip_api.errors import ApiProblem
from cip_api.settings import Settings
from cip_connectors.wizard import recognise_export
from cip_connectors.wizard.columns import FIELDS
from cip_connectors.wizard.roles import MINIMUM, Role, Sure

TABLE_SUFFIXES = (".csv", ".txt", ".tsv", ".xlsx")
UPLOAD_SUFFIXES = (*TABLE_SUFFIXES, ".zip")
MAX_NAME = 100
ROLES: tuple[Role, ...] = (
    "events",
    "hour_bookings",
    "steps",
    "calendar",
    "orders",
    "products",
    "routings",
    "teams",
    "team_shifts",
    "overtime",
    "capacity_costs",
    "changeovers",
    "outsourcing",
)


def clean_name(name: str) -> str | None:
    """A safe file name from what the client's computer called it: no folders, only letters,
    digits, dots, dashes and underscores (``Shop Floor (1).csv`` → ``Shop_Floor_1.csv``).
    None when the file is not a kind we read."""
    base = re.split(r"[\\/]", name)[-1].strip()
    stem, dot, suffix = base.rpartition(".")
    if not dot or f".{suffix.lower()}" not in UPLOAD_SUFFIXES:
        return None
    stem = re.sub(r"_+", "_", re.sub(r"[^A-Za-z0-9_.-]", "_", stem)).strip("._-") or "file"
    return f"{stem[: MAX_NAME - len(suffix) - 1]}.{suffix.lower()}"


class NotRead(BaseModel):
    """A file of the upload that is not a table, kept out with the reason."""

    name: str
    problem: Literal["not_a_table_file", "unreadable_zip"]


async def save_export(
    folder: Path, files: list[UploadFile], settings: Settings
) -> tuple[list[Path], list[NotRead]]:
    """Write the upload into the import's source folder. A zip is unpacked; files that are not
    tables are listed, not stored. Fails only when nothing in the upload is a table."""
    folder.mkdir(parents=True, exist_ok=True)
    limit = settings.max_upload_mb * 1024 * 1024
    written: list[Path] = []
    not_read: list[NotRead] = []
    for f in files:
        original = f.filename or ""
        name = clean_name(original)
        if name is None:
            not_read.append(NotRead(name=_shown(original), problem="not_a_table_file"))
            continue
        target = folder / name
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
        if name.endswith(".zip"):
            written += _unzip(part, folder, limit, not_read, original)
            part.unlink(missing_ok=True)
        else:
            part.replace(target)
            written.append(target)
    if not written:
        raise ApiProblem("no_table_files")
    return written, not_read


def _shown(name: str) -> str:
    return re.split(r"[\\/]", name)[-1][:MAX_NAME] or "file"


def _unzip(path: Path, folder: Path, limit: int, not_read: list[NotRead], shown: str) -> list[Path]:
    """Every table file in the zip, flattened into the folder; folders inside are ignored."""
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        not_read.append(NotRead(name=_shown(shown), problem="unreadable_zip"))
        return []
    written: list[Path] = []
    total = 0
    with archive:
        for info in archive.infolist():
            base = re.split(r"[\\/]", info.filename)[-1]
            if info.is_dir() or not base or base.startswith(".") or "__MACOSX" in info.filename:
                continue
            name = clean_name(base)
            if name is None or name.endswith(".zip"):
                not_read.append(NotRead(name=_shown(base), problem="not_a_table_file"))
                continue
            # Counted as written, not from the zip's own size field, which can lie.
            target = folder / name
            with archive.open(info) as src, target.open("wb") as out:
                while chunk := src.read(1024 * 1024):
                    total += len(chunk)
                    if total > limit:
                        out.close()
                        target.unlink(missing_ok=True)
                        for done in written:
                            done.unlink(missing_ok=True)
                        raise ApiProblem("file_too_large", limit_mb=limit // (1024 * 1024))
                    out.write(chunk)
            written.append(target)
    return written


# --- what was found ------------------------------------------------------------------------


class TableOut(BaseModel):
    table: str
    """``file`` or ``file#sheet``."""
    file: str
    sheet: str | None
    role: Role | None
    """None: the app cannot tell, or the client skipped it."""
    sure: Sure | None
    """sure (content and name agree), likely (content only), unsure (name only: asked),
    confirmed (the client said so); None when not placed."""
    skipped: bool = False
    reasons: list[str]
    rows: int
    columns: int
    personal_columns: int
    """How many personal columns were dropped on read (never their values)."""
    title_lines: int
    totals_lines: int
    problem: str | None


class LinkOut(BaseModel):
    table: str
    column: str
    to_table: str
    to_column: str
    found: int
    total: int
    is_list: bool


class MinimumRoleOut(BaseModel):
    key: Literal["events", "steps", "calendar"]
    tables: list[str]


class FoundColumnOut(BaseModel):
    """One column of a placed table and the field it fills (ADR-0011 §3)."""

    table: str
    column: str
    fields: list[str]
    """Standard fields this column fills (a station column can fill three); empty: none."""
    part: Literal["date", "time"] | None = None
    """The column is the date or the time half of the field, with another column."""
    sure: Sure | None
    source: Literal["rules", "ai", "client"]
    """Who suggested it: the rules, the AI (always to confirm) or the client."""
    reasons: list[str]
    ai_reason: str | None = None
    personal: bool = False
    """Dropped on read; never shown, stored or sent."""
    skipped: bool = False
    """The client said this column is not needed."""
    question: bool = False
    """The client should confirm or choose: not matched, matched from content only, or
    suggested by the AI."""


class AiOut(BaseModel):
    state: AiState
    """not_connected (no key: rules only), connected, limit_reached or error (rules only,
    for this upload)."""


class ConfirmedOut(BaseModel):
    by: str
    by_role: str | None = None
    """The role of who confirmed, for the page to name (never an internal id)."""
    at: str


class RecognisedOut(BaseModel):
    """What the app found in the upload (ADR-0011 §2-3)."""

    tables: list[TableOut]
    links: list[LinkOut]
    minimum: list[MinimumRoleOut]
    not_read: list[NotRead]
    to_answer: list[str]
    """Tables the client should name or skip: not placed, or placed by name only."""
    columns: list[FoundColumnOut] = []
    fields: dict[str, list[str]] = {}
    """For each role, the fields a column of that table can be: the client's choices."""
    column_questions: int = 0
    ai: AiOut = AiOut(state="not_connected")
    confirmed: ConfirmedOut | None = None
    """Who confirmed the summary and when; cleared by any later answer."""


class TableAnswer(BaseModel):
    table: str
    role: Role | Literal["skip"]


class ColumnAnswer(BaseModel):
    table: str
    column: str
    field: str
    """One of the table role's fields, or ``skip``: not needed."""


SEP = "\u001f"
"""Between table and column in the stored column answers."""


def role_fields(role: str | None) -> list[str]:
    return [f.target for f in FIELDS.get(role, ())] if role else []  # type: ignore[call-overload]


def recognise_folder(
    folder: Path,
    not_read: list[NotRead],
    answers: dict[str, str],
    column_answers: dict[str, str],
    ai: Ai,
) -> dict[str, Any]:
    """Recognise every table in the import's source folder and match its columns, with the
    roles the client gave; stored as JSON with the import. Columns the rules cannot match go to
    the AI when it is connected; it only suggests."""
    found = recognise_export(
        sorted(p for p in folder.iterdir() if p.suffix in TABLE_SUFFIXES),
        answers,  # type: ignore[arg-type]
    )
    tables = []
    for t in found.tables:
        r = found.role_of(t.id)
        tables.append(
            TableOut(
                table=t.id,
                file=t.file,
                sheet=t.sheet,
                role=r.role if r else None,
                sure=r.sure if r else None,
                reasons=r.reasons if r else [],
                rows=len(t.rows),
                columns=len(t.header),
                personal_columns=len(t.personal_columns),
                title_lines=t.title_lines,
                totals_lines=t.totals_lines,
                problem=t.problem,
            ).model_dump()
        )
    columns: list[dict[str, Any]] = [
        {
            "table": m.table,
            "column": m.column,
            "target": m.target,
            "sure": m.sure,
            "reasons": m.reasons,
            "personal": m.personal,
            "source": "rules",
            "ai_reason": None,
        }
        for m in found.columns
    ]
    _ask_ai(found, columns, ai)
    return {
        "tables": tables,
        "links": [LinkOut(**vars(link)).model_dump() for link in found.links],
        "columns": columns,
        "not_read": [n.model_dump() for n in not_read],
        "answers": answers,
        "column_answers": column_answers,
        "ai": {"state": ai.state, "spent_eur": round(ai.budget.spent_eur, 4)},
        "confirmed": None,
    }


def _ask_ai(found: Any, columns: list[dict[str, Any]], ai: Ai) -> None:
    """Columns the rules did not match, with the fields still free in their table."""
    free: dict[str, set[str]] = {}
    for c in columns:
        for f in _flat(c["target"]):
            free.setdefault(c["table"], set()).add(f)
    open_columns = []
    for c in columns:
        r = found.role_of(c["table"])
        if c["target"] is not None or c["personal"] or r is None or r.role is None:
            continue
        table = next(t for t in found.tables if t.id == c["table"])
        values = frozenset(str(row.get(c["column"]) or "") for row in table.rows[:200])
        fields = [f for f in role_fields(r.role) if f not in free.get(c["table"], set())]
        if fields:
            open_columns.append(OpenColumn(c["table"], r.role, c["column"], values, fields))
    if not open_columns:
        return
    try:
        suggestions = suggest_columns(ai, open_columns)
    except AiUnavailableError:
        return
    by = {(c["table"], c["column"]): c for c in columns}
    for s in suggestions:
        c = by[(s.table, s.column)]
        c.update(target=s.target, sure=s.sure, source="ai", ai_reason=s.reason)


def _flat(target: Any) -> list[str]:
    if isinstance(target, str):
        return [target]
    if isinstance(target, list):
        return [str(t) for t in target]
    if isinstance(target, dict):
        return [str(t) for t in target.values()]
    return []


def recognised_out(stored: dict[str, Any] | None) -> RecognisedOut | None:
    """The stored recognition with the client's answers applied."""
    if not stored:
        return None
    answers: dict[str, str] = stored.get("answers", {})
    tables = []
    for raw in stored["tables"]:
        t = TableOut.model_validate(raw)
        answer = answers.get(t.table)
        if answer == "skip":
            t.role, t.sure, t.skipped = None, "confirmed", True
        elif answer in ROLES:
            t.role, t.sure = answer, "confirmed"
        tables.append(t)
    minimum = [
        MinimumRoleOut(
            key=key,  # type: ignore[arg-type]
            tables=[t.table for t in tables if t.role in roles and t.sure != "unsure"],
        )
        for key, roles in MINIMUM
    ]
    placed = {t.table for t in tables if t.role is not None and t.sure != "unsure"}
    column_answers: dict[str, str] = stored.get("column_answers", {})
    columns = []
    for raw in stored.get("columns", []):
        if raw["table"] not in placed:
            continue
        target = raw["target"]
        part = None
        if isinstance(target, dict):
            ((key, target),) = target.items()
            part = "date" if key.startswith("date") else "time"
        c = FoundColumnOut(
            table=raw["table"],
            column=raw["column"],
            fields=[] if raw["personal"] else _flat(target),
            part=part,  # type: ignore[arg-type]
            sure=raw["sure"],
            source=raw["source"],
            reasons=raw["reasons"],
            ai_reason=raw.get("ai_reason"),
            personal=raw["personal"],
        )
        answer = column_answers.get(f"{c.table}{SEP}{c.column}")
        if answer == "skip":
            c.fields, c.part, c.sure, c.source, c.skipped = [], None, "confirmed", "client", True
        elif answer is not None:
            if answer not in c.fields:
                c.fields, c.part = [answer], None
            c.sure, c.source = "confirmed", "client"
        c.question = not c.personal and (c.sure in (None, "likely", "unsure"))
        columns.append(c)
    roles = {t.role for t in tables if t.role is not None}
    confirmed = stored.get("confirmed")
    return RecognisedOut(
        tables=tables,
        links=[LinkOut.model_validate(link) for link in stored["links"]],
        minimum=minimum,
        not_read=[NotRead.model_validate(n) for n in stored.get("not_read", [])],
        to_answer=[
            t.table
            for t in tables
            if t.problem is None and not t.skipped and t.sure in (None, "unsure")
        ],
        columns=columns,
        fields={r: role_fields(r) for r in sorted(roles)},
        column_questions=sum(c.question for c in columns),
        ai=AiOut(state=stored.get("ai", {}).get("state", "not_connected")),
        confirmed=ConfirmedOut.model_validate(confirmed) if confirmed else None,
    )
