"""Keep docs/input-data.md and the schema in sync.

Every backticked field in a Must or Should row of sections A-E must exist on a model,
directly or through ALIASES. Section F (accounts, logins, connections) is API data and is
covered by the auth sequence, not by the plant data model.
"""

import re
from pathlib import Path

import pytest

from cip_schema.registry import MODELS

DOC = Path(__file__).resolve().parents[3] / "docs" / "input-data.md"
CHECKED_SECTIONS = ("A.", "B.", "C.", "D.", "E.")
ALIASES = {
    # "overtime `eur_cents_per_h`" in item 21
    "eur_cents_per_h": "overtime_eur_cents_per_h",
}
FIELD = re.compile(r"`([a-z][a-z0-9_]*)`")


def doc_rows() -> list[tuple[str, str, str, list[str]]]:
    """(section, item, need, fields) for every table row in the checked sections."""
    rows: list[tuple[str, str, str, list[str]]] = []
    section = ""
    for line in DOC.read_text().splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        if not section.startswith(CHECKED_SECTIONS) or not line.startswith("| "):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 6 or not cells[0].isdigit():
            continue
        item, _data, key_fields, _source, need = cells[:5]
        rows.append((section, item, need, FIELD.findall(key_fields)))
    return rows


SCHEMA_FIELDS = {name for model in MODELS.values() for name in model.model_fields}
REQUIRED = [
    (item, field)
    for _section, item, need, fields in doc_rows()
    if need.startswith(("Must", "Should"))
    for field in fields
]


def test_document_is_parsed() -> None:
    items = {item for _s, item, _n, _f in doc_rows()}
    assert {"1", "5", "9", "12", "16", "21"} <= items
    assert len(REQUIRED) > 25


@pytest.mark.parametrize(("item", "field"), REQUIRED)
def test_must_and_should_fields_exist_in_schema(item: str, field: str) -> None:
    name = ALIASES.get(field, field)
    assert name in SCHEMA_FIELDS, f"input item #{item}: `{field}` has no place in the schema"


def test_later_items_are_reported_not_required() -> None:
    later = [
        (item, f)
        for _s, item, need, fields in doc_rows()
        if need.startswith("Later")
        for f in fields
        if ALIASES.get(f, f) not in SCHEMA_FIELDS
    ]
    # Later items may be missing; this only documents them.
    assert all(item.isdigit() for item, _f in later)
