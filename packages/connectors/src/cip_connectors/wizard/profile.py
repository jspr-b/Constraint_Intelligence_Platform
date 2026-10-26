"""What each column holds, from its values: times, numbers, codes or text (ADR-0011 §3).

A profile never keeps more than the distinct values needed to find links between tables, and
it is only made from columns that are not personal (they are dropped on read).
"""

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from cip_connectors.convert import Cell
from cip_connectors.wizard.tables import ExportTable

Kind = Literal["datetime", "date", "time", "int", "decimal", "text", "empty"]
SAMPLE = 400
"""Values looked at to decide a column's kind."""
SHARE = 0.95
"""Share of the sampled values that must fit a kind."""
MAX_VALUES = 50_000

_D = r"\d{1,4}[-./]\d{1,2}[-./]\d{1,4}"
_T = r"\d{1,2}:\d{2}(:\d{2}(\.\d+)?)?(\s?[AaPp][Mm])?"
PATTERNS: tuple[tuple[Kind, re.Pattern[str]], ...] = (
    ("datetime", re.compile(rf"{_D}[ T]{_T}(Z|[+-]\d{{2}}:?\d{{2}})?")),
    ("date", re.compile(_D)),
    ("time", re.compile(_T)),
    ("int", re.compile(r"[-+]?\d+")),
    ("decimal", re.compile(r"[-+]?(\d{1,3}([.,  ]\d{3})*|\d+)([.,]\d+)?")),
)


def norm(value: Cell) -> str:
    """A value as text for comparing across files: ``24000``, ``24000.0`` and ``"24000"`` are
    the same order number; spaces around a value do not count."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    return str(value).strip()


@dataclass
class ColumnProfile:
    name: str
    kind: Kind
    filled: int
    """Rows with a value."""
    distinct: int
    values: frozenset[str] = field(repr=False)
    """Distinct values, normalised (see ``norm``)."""
    top_share: float
    """Share of the filled rows taken by the most common value."""

    @property
    def unique(self) -> bool:
        """Every filled row has its own value: a key such as a step code or a job number."""
        return self.filled >= 2 and self.distinct == self.filled

    @property
    def is_time(self) -> bool:
        return self.kind in ("datetime", "date", "time")

    @property
    def is_number(self) -> bool:
        return self.kind in ("int", "decimal")


def _kind_of(value: Cell) -> Kind:
    if isinstance(value, datetime):
        return "datetime" if (value.hour, value.minute, value.second) != (0, 0, 0) else "date"
    if isinstance(value, bool):
        return "text"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "int" if value.is_integer() else "decimal"
    text = str(value).strip()
    for kind, pattern in PATTERNS:
        if pattern.fullmatch(text):
            return kind
    return "text"


def _column_kind(values: Sequence[Cell]) -> Kind:
    if not values:
        return "empty"
    kinds = Counter(_kind_of(v) for v in values[:SAMPLE])
    n = sum(kinds.values())
    # A date column with some times is a datetime column (midnight shows as a date in Excel).
    if kinds["datetime"] and kinds["datetime"] + kinds["date"] >= SHARE * n:
        return "datetime"
    if kinds["int"] and kinds["int"] + kinds["decimal"] >= SHARE * n and kinds["decimal"]:
        return "decimal"
    kind, count = kinds.most_common(1)[0]
    return kind if count >= SHARE * n else "text"


def profile(table: ExportTable) -> dict[str, ColumnProfile]:
    out = {}
    for name in table.header:
        values = [v for r in table.rows if (v := r.get(name)) not in (None, "")]
        counts = Counter(norm(v) for v in values)
        out[name] = ColumnProfile(
            name=name,
            kind=_column_kind(values),
            filled=len(values),
            distinct=len(counts),
            values=frozenset(list(counts)[:MAX_VALUES]),
            top_share=(counts.most_common(1)[0][1] / len(values)) if values else 0.0,
        )
    return out
