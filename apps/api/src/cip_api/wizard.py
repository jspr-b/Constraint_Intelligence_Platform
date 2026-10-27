"""Mapping wizard (ADR-0011): take the whole export as it comes and say what each table is and
how the tables link (§2), which field each column fills (§3), and what the plant's codes and
formats mean (§4). The client names or skips what the app cannot place, and confirms.

The recognition is stored with the import (``imports.wizard``), with the client's answers, so
the page shows it without reading the files again.
"""

import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import UploadFile
from pydantic import BaseModel, Field

from cip_api.ai import (
    Ai,
    AiState,
    AiUnavailableError,
    OpenCode,
    OpenColumn,
    suggest_codes,
    suggest_columns,
)
from cip_api.errors import ApiProblem
from cip_api.settings import Settings
from cip_connectors.wizard import recognise_export
from cip_connectors.wizard.codes import CODE_FIELDS, MEANINGS, code_values, meaning_of, yes_no
from cip_connectors.wizard.columns import FIELDS
from cip_connectors.wizard.formats import day_first, is_time_field, unit_of
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


class FoundCodeOut(BaseModel):
    """One code of a status column and what it means (ADR-0011 §4)."""

    target: str
    """The status field: ``events.event_type``, ``orders.status``, ``calendar.kind`` or
    ``resources.kind``."""
    table: str
    column: str
    code: str
    """As written in the export."""
    meaning: str | None
    """None: not known yet; asked. Rows with an unanswered code are not used."""
    sure: Sure | None
    source: Literal["rules", "ai", "client"]
    reasons: list[str]
    ai_reason: str | None = None
    rows: int
    skipped: bool = False
    """The client said: leave the rows with this code out."""
    question: bool = False


class FoundStepOut(BaseModel):
    """A step of the steps list, with the plant's own code (ADR-0011 §4: never invented)."""

    code: str
    name: str | None
    station: str | None
    kind: Literal["machine", "manual"] | None
    """None: the export does not say; the client may."""
    changed: bool = False
    """The client gave the name or kind."""


class TimeFormatOut(BaseModel):
    table: str
    column: str
    part: Literal["date", "time"] | None
    format: str | None
    """A ``strftime`` format; None while the date order is asked."""
    options: list[str]
    sure: Sure | None
    example: str | None
    """One value as written in the export."""
    example_read: str | None = None
    """That value as read, ``YYYY-MM-DDTHH:MM`` in plant time, for the page to word."""
    real_dates: bool = False


class UnitOut(BaseModel):
    table: str
    column: str
    target: str
    unit: Literal["min", "h"]
    field_unit: Literal["min", "h"]
    sure: Sure
    """sure: the column name says; likely: the field's own unit, assumed; confirmed: the
    client said."""


class FormatsOut(BaseModel):
    """How the export writes dates, times and numbers (ADR-0011 §4)."""

    times: list[TimeFormatOut]
    """Columns used as a time."""
    date_order: Literal["day", "month"] | None = None
    """The client's answer when the values do not tell day-month from month-day."""
    date_order_question: bool = False
    date_example: str | None = None
    """A value that reads both ways, for the question."""
    date_readings: dict[str, str] = {}
    """That value read day-month (``day``) and month-day (``month``)."""
    decimal: Literal[",", "."]
    decimal_question: bool = False
    delimiter: str | None
    title_lines: int
    totals_line: bool
    byte_order_mark: bool
    units: list[UnitOut]
    yes_words: list[str]
    no_words: list[str]
    timezone: str | None = None
    """The plant's, from Plant setup: times are read in it and stored as UTC."""


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
    codes: list[FoundCodeOut] = []
    meanings: dict[str, list[str]] = {}
    """For each status field, the meanings a code can have: the client's choices."""
    code_questions: int = 0
    steps: list[FoundStepOut] = []
    formats: FormatsOut | None = None
    format_questions: int = 0


class TableAnswer(BaseModel):
    table: str
    role: Role | Literal["skip"]


class CodeAnswer(BaseModel):
    target: str
    code: str
    meaning: str
    """One of the field's meanings, or ``skip``: leave the rows with this code out."""


class FormatAnswer(BaseModel):
    """One answer at a time: the date order, the decimal mark, or a duration column's unit."""

    date_order: Literal["day", "month"] | None = None
    decimal: Literal[",", "."] | None = None
    table: str | None = None
    column: str | None = None
    unit: Literal["min", "h"] | None = None


class StepAnswer(BaseModel):
    code: str
    name: str | None = Field(default=None, min_length=1, max_length=80)
    kind: Literal["machine", "manual"] | None = None


class ColumnAnswer(BaseModel):
    table: str
    column: str
    field: str
    """One of the table role's fields, or ``skip``: not needed."""


SEP = "\u001f"
"""Between table and column in the stored column answers."""


def role_fields(role: str | None) -> list[str]:
    return [f.target for f in FIELDS.get(role, ())] if role else []  # type: ignore[call-overload]


ANSWER_KEYS = ("code_answers", "format_answers", "step_answers")
"""Answers about codes, formats and steps, kept as they are when the upload is read again."""


def recognise_folder(
    folder: Path,
    not_read: list[NotRead],
    answers: dict[str, str],
    column_answers: dict[str, str],
    ai: Ai,
    kept: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Recognise every table in the import's source folder and match its columns, with the
    roles the client gave; stored as JSON with the import. Columns and codes the rules cannot
    place go to the AI when it is connected; it only suggests. ``kept`` holds the answers about
    codes, formats and steps."""
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
    values = code_values(found.tables)
    f = found.formats
    return {
        "code_values": [
            {"table": table, "column": column, "codes": codes}
            for (table, column), codes in values.items()
        ],
        "ai_codes": _ask_ai_codes(found, ai),
        "steps": [vars(s) for s in found.steps],
        "formats": {
            "times": [vars(tf) for tf in f.times],
            "decimal": f.decimal,
            "decimal_sure": f.decimal_sure,
            "delimiter": f.delimiter,
            "title_lines": f.title_lines,
            "totals_line": f.totals_line,
            "byte_order_mark": f.byte_order_mark,
        },
        **{k: (kept or {}).get(k, {}) for k in ANSWER_KEYS},
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


def _ask_ai_codes(found: Any, ai: Ai) -> dict[str, dict[str, Any]]:
    """AI meanings for the codes the rules do not know, keyed ``field SEP code``."""
    open_codes: dict[tuple[str, str, str], list[str]] = {}
    for c in found.codes:
        if c.meaning is None:
            open_codes.setdefault((c.target, c.table, c.column), []).append(c.code)
    if not open_codes:
        return {}
    asked = [
        OpenCode(target, table, column, codes, list(MEANINGS[target]))
        for (target, table, column), codes in open_codes.items()
    ]
    try:
        suggestions = suggest_codes(ai, asked)
    except AiUnavailableError:
        return {}
    return {
        f"{s.target}{SEP}{s.code}": {"meaning": s.meaning, "sure": s.sure, "reason": s.reason}
        for s in suggestions
    }


def _flat(target: Any) -> list[str]:
    if isinstance(target, str):
        return [target]
    if isinstance(target, list):
        return [str(t) for t in target]
    if isinstance(target, dict):
        return [str(t) for t in target.values()]
    return []


def recognised_out(
    stored: dict[str, Any] | None, timezone: str | None = None
) -> RecognisedOut | None:
    """The stored recognition with the client's answers applied. ``timezone`` is the plant's."""
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
    codes = _codes_out(stored, columns)
    formats = _formats_out(stored, columns, timezone)
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
        codes=codes,
        meanings={f: list(MEANINGS[f]) for f in sorted({c.target for c in codes})},
        code_questions=sum(c.question for c in codes),
        steps=_steps_out(stored),
        formats=formats,
        format_questions=_format_questions(formats),
    )


def _codes_out(stored: dict[str, Any], columns: list[FoundColumnOut]) -> list[FoundCodeOut]:
    """The codes of every column used as a status field, with the rules', the AI's or the
    client's meaning. A code is never left out: without a meaning it is a question."""
    values = {(v["table"], v["column"]): v["codes"] for v in stored.get("code_values", [])}
    ai: dict[str, dict[str, Any]] = stored.get("ai_codes", {})
    answers: dict[str, str] = stored.get("code_answers", {})
    out = []
    for c in columns:
        if c.personal or c.skipped:
            continue
        for target in (f for f in c.fields if f in CODE_FIELDS):
            for code, rows in values.get((c.table, c.column), {}).items():
                meaning, sure, reason = meaning_of(target, code)
                found = FoundCodeOut(
                    target=target,
                    table=c.table,
                    column=c.column,
                    code=code,
                    meaning=meaning,
                    sure=sure,
                    source="rules",
                    reasons=[reason],
                    rows=rows,
                )
                key = f"{target}{SEP}{code}"
                if meaning is None and key in ai:
                    found.meaning, found.sure = ai[key]["meaning"], ai[key]["sure"]
                    found.source, found.ai_reason = "ai", ai[key]["reason"]
                answer = answers.get(key)
                if answer == "skip":
                    found.meaning, found.sure, found.source, found.skipped = (
                        None,
                        "confirmed",
                        "client",
                        True,
                    )
                elif answer is not None:
                    found.meaning, found.sure, found.source = answer, "confirmed", "client"
                found.question = not found.skipped and found.sure in (None, "likely", "unsure")
                out.append(found)
    return out


def _steps_out(stored: dict[str, Any]) -> list[FoundStepOut]:
    answers: dict[str, dict[str, Any]] = stored.get("step_answers", {})
    out = []
    for raw in stored.get("steps", []):
        step = FoundStepOut.model_validate(raw)
        given = answers.get(step.code, {})
        if given:
            step.name = given.get("name") or step.name
            step.kind = given.get("kind") or step.kind
            step.changed = True
        out.append(step)
    return out


def _read(example: str | None, fmt: str | None) -> str | None:
    """A value as read with a format: ``YYYY-MM-DDTHH:MM``, ``YYYY-MM-DD`` or ``HH:MM``."""
    if example is None or fmt is None:
        return None
    try:
        at = datetime.strptime(example, fmt)
    except ValueError:
        return None
    has_date = any(d in fmt for d in ("%d", "%Y", "%y"))
    has_time = any(h in fmt for h in ("%H", "%I"))
    if has_date and has_time:
        return at.strftime("%Y-%m-%dT%H:%M")
    return at.strftime("%Y-%m-%d") if has_date else at.strftime("%H:%M")


def _formats_out(
    stored: dict[str, Any], columns: list[FoundColumnOut], timezone: str | None
) -> FormatsOut | None:
    f = stored.get("formats")
    if not f:
        return None
    answers: dict[str, Any] = stored.get("format_answers", {})
    order = answers.get("date_order")
    by_column = {(x["table"], x["column"]): x for x in f["times"]}
    times, units = [], []
    asked_example = None
    readings: dict[str, str] = {}
    for c in columns:
        if c.personal or c.skipped:
            continue
        for target in c.fields:
            given = answers.get("units", {}).get(f"{c.table}{SEP}{c.column}")
            unit = unit_of(c.table, c.column, target)
            if unit:
                units.append(
                    UnitOut(
                        table=c.table,
                        column=c.column,
                        target=target,
                        unit=given or unit.unit,  # type: ignore[arg-type]
                        field_unit=unit.field_unit,  # type: ignore[arg-type]
                        sure="confirmed" if given else unit.sure,
                    )
                )
        if c.part is None and not any(is_time_field(x) for x in c.fields):
            continue
        x = by_column.get((c.table, c.column), {})
        fmt, sure, options = x.get("format"), x.get("sure"), x.get("options", [])
        if fmt is None and len(options) == 2 and order is not None:
            fmt = next(o for o in options if day_first(o) == (order == "day"))
            sure = "confirmed"
        elif fmt is None and len(options) == 2 and asked_example is None:
            asked_example = x.get("example")
            for o in options:
                read = _read(asked_example, o)
                if read:
                    readings["day" if day_first(o) else "month"] = read
        times.append(
            TimeFormatOut(
                table=c.table,
                column=c.column,
                part=c.part,
                format=fmt,
                options=options,
                sure=sure,
                example=x.get("example"),
                example_read=_read(x.get("example"), fmt),
                real_dates=x.get("real_dates", False),
            )
        )
    values = {(v["table"], v["column"]): v["codes"] for v in stored.get("code_values", [])}
    words = [
        w
        for c in columns
        if "calendar.covered" in c.fields and not c.skipped
        for w in values.get((c.table, c.column), {})
    ]
    decimal = answers.get("decimal") or f["decimal"]
    return FormatsOut(
        times=times,
        date_order=order,
        date_order_question=asked_example is not None,
        date_example=asked_example,
        date_readings=readings,
        decimal=decimal,
        decimal_question=f["decimal_sure"] is None and "decimal" not in answers,
        delimiter=f["delimiter"],
        title_lines=f["title_lines"],
        totals_line=f["totals_line"],
        byte_order_mark=f["byte_order_mark"],
        units=units,
        yes_words=sorted(w for w in words if yes_no(w) is True),
        no_words=sorted(w for w in words if yes_no(w) is False),
        timezone=timezone,
    )


def _format_questions(formats: FormatsOut | None) -> int:
    """Open questions about formats: the date order, the decimal mark, and each time column
    whose values fit no format (to skip, or fix in the export)."""
    if formats is None:
        return 0
    unreadable = sum(1 for t in formats.times if t.format is None and len(t.options) != 2)
    return int(formats.date_order_question) + int(formats.decimal_question) + unreadable
