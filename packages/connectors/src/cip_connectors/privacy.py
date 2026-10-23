"""Personal data filter (ADR-0005).

Columns that identify a person are dropped when a source table is read, before any row is
parsed: their values never reach the standard layout, the import report, logs or errors.
A column is personal when its name matches the denylist (English and Dutch) or when the
mapping lists it in ``personal_columns``.
"""

import re

from cip_connectors.readers import DropRule
from cip_schema.types import PERSON_WORDS

DENYLIST = PERSON_WORDS


def _normalise(column: str) -> str:
    return re.sub(r"[^a-z0-9]", "", column.lower())


def is_personal(column: str, marked: frozenset[str] = frozenset()) -> bool:
    name = _normalise(column)
    return name in marked or any(word in name for word in DENYLIST)


def personal_column_rule(extra: tuple[str, ...] = ()) -> DropRule:
    marked = frozenset(_normalise(c) for c in extra)

    def drop(column: str) -> bool:
        return is_personal(column, marked)

    return drop
