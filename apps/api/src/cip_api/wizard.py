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

from cip_api.errors import ApiProblem
from cip_api.settings import Settings
from cip_connectors.wizard import recognise_export
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


class RecognisedOut(BaseModel):
    """What the app found in the upload (ADR-0011 §2)."""

    tables: list[TableOut]
    links: list[LinkOut]
    minimum: list[MinimumRoleOut]
    not_read: list[NotRead]
    to_answer: list[str]
    """Tables the client should name or skip: not placed, or placed by name only."""


class TableAnswer(BaseModel):
    table: str
    role: Role | Literal["skip"]


def recognise_folder(
    folder: Path, not_read: list[NotRead], answers: dict[str, str]
) -> dict[str, Any]:
    """Recognise every table in the import's source folder; stored as JSON with the import."""
    found = recognise_export(sorted(p for p in folder.iterdir() if p.suffix in TABLE_SUFFIXES))
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
    links = [LinkOut(**vars(link)).model_dump() for link in found.links]
    return {
        "tables": tables,
        "links": links,
        "not_read": [n.model_dump() for n in not_read],
        "answers": answers,
    }


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
    )
