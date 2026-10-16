"""Read source tables. Personal columns are dropped at read time: their values never enter a row.

Files come as plants send them: CSV in UTF-8 or Windows-1252 (Dutch Excel), with the expected
separator or another one, or Excel. When a file cannot be read, ``inspect_file`` says why.
"""

import csv
import io
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from cip_connectors.convert import Cell

ENCODINGS = ("utf-8-sig", "cp1252", "latin-1")
SEPARATORS = (";", ",", "\t", "|")


@dataclass
class SourceTable:
    name: str
    path: Path
    header: list[str]
    rows: list[tuple[int, dict[str, Cell]]]
    """(line number in the source file, column → value), personal columns removed."""
    dropped_columns: list[str] = field(default_factory=list)
    encoding: str | None = None
    delimiter: str | None = None


DropRule = Callable[[str], bool]


class UnreadableFileError(ValueError):
    """A file that cannot be read as a table; ``problem`` is a stable code for the UI."""

    def __init__(self, problem: str) -> None:
        super().__init__(problem)
        self.problem = problem


def _split(header: list[str], drop: DropRule) -> tuple[list[int], list[str]]:
    keep = [i for i, name in enumerate(header) if not drop(name)]
    return keep, [header[i] for i in range(len(header)) if i not in keep]


def decode(raw: bytes) -> tuple[str, str]:
    """Text and the encoding that read it: UTF-8 (with or without BOM), else Windows-1252."""
    if b"\x00" in raw[:4096]:
        raise UnreadableFileError("not_text")
    for encoding in ENCODINGS:
        try:
            return raw.decode(encoding), encoding.replace("-sig", "")
        except UnicodeDecodeError:
            continue
    raise UnreadableFileError("not_text")  # pragma: no cover  (latin-1 decodes every byte)


def choose_delimiter(first_line: str, preferred: str) -> str:
    """The mapping's separator, unless it gives one column and another separator gives more."""
    if len(first_line.split(preferred)) > 1:
        return preferred
    counts = {d: len(first_line.split(d)) for d in SEPARATORS}
    best = max(counts, key=lambda d: counts[d])
    return best if counts[best] > 1 else preferred


def read_csv(path: Path, delimiter: str, drop: DropRule) -> SourceTable:
    text, encoding = decode(path.read_bytes())
    first = text.lstrip("﻿").split("\n", 1)[0].rstrip("\r")
    if not first.strip():
        raise UnreadableFileError("empty" if not text.strip() else "no_header")
    used = choose_delimiter(first, delimiter)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=used)
    header = [h.strip() for h in next(reader, [])]
    keep, dropped = _split(header, drop)
    rows: list[tuple[int, dict[str, Cell]]] = []
    for line, values in enumerate(reader, start=2):
        if not any(v.strip() for v in values):
            continue
        rows.append((line, {header[i]: values[i] if i < len(values) else "" for i in keep}))
    return SourceTable(path.stem, path, [header[i] for i in keep], rows, dropped, encoding, used)


@dataclass(frozen=True)
class FileInspection:
    """What a file is, before anything is imported. Values of personal columns are never read."""

    readable: bool
    problem: str | None
    """empty, no_header, not_text, single_column, unreadable_excel; None when readable."""
    encoding: str | None
    delimiter: str | None
    header: list[str]
    """All column names, personal ones included (names only)."""
    personal_columns: list[str]
    rows: int
    preview: list[dict[str, str]]
    """Up to 5 data rows, personal columns left out."""


def inspect_file(path: Path, delimiter: str, drop: DropRule) -> FileInspection:
    try:
        if path.suffix.lower() == ".xlsx":
            from cip_connectors.excel import read_xlsx

            try:
                table = read_xlsx(path, drop)
            except Exception as exc:  # corrupt, password-protected or not an Excel file
                raise UnreadableFileError("unreadable_excel") from exc
            if not table.header:
                raise UnreadableFileError("no_header")
        else:
            table = read_csv(path, delimiter, drop)
    except UnreadableFileError as exc:
        return FileInspection(False, exc.problem, None, None, [], [], 0, [])
    header = table.header + table.dropped_columns
    problem = "single_column" if len(header) == 1 and path.suffix.lower() != ".xlsx" else None
    preview = [
        {k: "" if v is None else str(v) for k, v in values.items()}
        for _line, values in table.rows[:5]
    ]
    return FileInspection(
        readable=problem is None,
        problem=problem,
        encoding=table.encoding,
        delimiter=table.delimiter,
        header=header,
        personal_columns=table.dropped_columns,
        rows=len(table.rows),
        preview=preview,
    )


def find_source(export_dir: Path, name: str) -> Path | None:
    for suffix in (".csv", ".xlsx"):
        candidate = export_dir / f"{name}{suffix}"
        if candidate.exists():
            return candidate
    return None
