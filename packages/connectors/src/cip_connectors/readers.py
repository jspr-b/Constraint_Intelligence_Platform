"""Read source tables. Personal columns are dropped at read time: their values never enter a row."""

import csv
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from cip_connectors.convert import Cell


@dataclass
class SourceTable:
    name: str
    path: Path
    header: list[str]
    rows: list[tuple[int, dict[str, Cell]]]
    """(line number in the source file, column → value), personal columns removed."""
    dropped_columns: list[str] = field(default_factory=list)


DropRule = Callable[[str], bool]


def _split(header: list[str], drop: DropRule) -> tuple[list[int], list[str]]:
    keep = [i for i, name in enumerate(header) if not drop(name)]
    return keep, [header[i] for i in range(len(header)) if i not in keep]


def read_csv(path: Path, delimiter: str, drop: DropRule) -> SourceTable:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.reader(fh, delimiter=delimiter)
        header = [h.strip() for h in next(reader, [])]
        keep, dropped = _split(header, drop)
        rows: list[tuple[int, dict[str, Cell]]] = []
        for line, values in enumerate(reader, start=2):
            if not any(v.strip() for v in values):
                continue
            rows.append((line, {header[i]: values[i] if i < len(values) else "" for i in keep}))
    return SourceTable(path.stem, path, [header[i] for i in keep], rows, dropped)


def find_source(export_dir: Path, name: str) -> Path | None:
    for suffix in (".csv", ".xlsx"):
        candidate = export_dir / f"{name}{suffix}"
        if candidate.exists():
            return candidate
    return None
