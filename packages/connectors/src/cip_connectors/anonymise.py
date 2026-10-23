"""Anonymise a factory export before anyone works with it (real-export intake).

Driven by the mapping that will import the export:

* personal columns are dropped (the same rule as the import, ADR-0005);
* columns the mapping does not read are dropped too: nobody has checked what is in them;
* every column that feeds a code or a name (machines, stations, products, orders, families)
  gets a stable pseudonym, the same in every file;
* numbers, times, statuses and reason codes are kept as they are, so every calculation on the
  anonymised export gives the same result as on the original.

Pseudonyms are a keyed hash (HMAC-SHA256) of the value: under the same key the same value always
gets the same pseudonym, and without the key nobody can trace a pseudonym back. The key stays
with the client. The anonymised mapping written next to the files maps the pseudonyms onto
themselves (machines onto neutral numbers), so the anonymised export imports as it is.
"""

import csv
import hashlib
import hmac
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml

from cip_connectors.convert import Cell
from cip_connectors.mapping import MappingSet, TableMapping
from cip_connectors.privacy import personal_column_rule
from cip_connectors.readers import SourceTable, find_source, read_csv

# Standard fields that carry a plant's own codes or names, and the pseudonym prefix per kind.
# Codes win over names when one column feeds both (e.g. a department used as station code
# and station name).
CODE_FIELDS = {
    "resource_code": "RES",
    "alternative_resource_codes": "RES",
    "station_code": "STN",
    "sku": "SKU",
    "order_id": "ORD",
    "family": "FAM",
    "setup_family": "SET",
    "from_setup_family": "SET",
    "to_setup_family": "SET",
}
NAME_PREFIX = {"resources": "Machine", "stations": "Station", "products": "Product"}
SHORT_CODES = {"RES": "MCH"}
"""Kinds whose standard code has a fixed form (machines: ``PNT-01``): the anonymised mapping
numbers their pseudonyms ``MCH-01``, ``MCH-02``… in pseudonym order, which says nothing about
the original codes."""
DIGITS = 10
"""Hex digits per pseudonym: 10 (40 bits) keeps clashes negligible for a million orders."""


class AnonymiseError(ValueError):
    pass


@dataclass
class FileReport:
    rows: int
    pseudonymised: list[str]
    kept: list[str]
    dropped_personal: list[str]
    dropped_unused: list[str]


@dataclass
class AnonymiseReport:
    files: dict[str, FileReport] = field(default_factory=dict)
    not_copied: list[str] = field(default_factory=list)
    """Files in the export the mapping does not read: left out, never copied."""
    pseudonyms: dict[str, int] = field(default_factory=dict)
    """How many distinct values got a pseudonym, per kind (no values themselves)."""

    def to_dict(self) -> dict[str, object]:
        return {
            "files": {name: vars(f) for name, f in self.files.items()},
            "not_copied": self.not_copied,
            "pseudonyms": self.pseudonyms,
        }


class Pseudonyms:
    """Stable keyed pseudonyms per kind; raises on the (unlikely) clash instead of merging."""

    def __init__(self, key: bytes) -> None:
        if len(key) < 16:
            raise AnonymiseError("the key must be at least 16 bytes")
        self._key = key
        self._seen: dict[str, dict[str, str]] = {}

    def __call__(self, kind: str, value: str) -> str:
        seen = self._seen.setdefault(kind, {})
        digest = hmac.new(self._key, f"{kind}\x00{value}".encode(), hashlib.sha256).hexdigest()
        pseudonym = f"{kind}-{digest[:DIGITS].upper()}"
        if seen.get(pseudonym, value) != value:
            raise AnonymiseError(f"two {kind} values got the same pseudonym; use a new key")
        seen[pseudonym] = value
        return pseudonym

    def counts(self) -> dict[str, int]:
        return {kind: len(values) for kind, values in sorted(self._seen.items())}


def column_kinds(mapping: MappingSet) -> tuple[dict[tuple[str, str], str], dict[str, set[str]]]:
    """(source table, column) → pseudonym kind, and the columns each source table reads."""
    kinds: dict[tuple[str, str], str] = {}
    names: dict[tuple[str, str], str] = {}
    read: dict[str, set[str]] = {}
    for table in mapping.tables:
        for name, rule in table.fields.items():
            if rule.from_ is None:
                continue
            read.setdefault(table.source, set()).add(rule.from_)
            key = (table.source, rule.from_)
            if name in CODE_FIELDS:
                kinds[key] = CODE_FIELDS[name]
            elif name == "name":
                names[key] = NAME_PREFIX.get(table.target, "Name")
    for key, kind in names.items():
        kinds.setdefault(key, kind)
    return kinds, read


def _text(value: Cell) -> str:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return "" if value is None else str(value).strip()


def _replace(value: Cell, kind: str, rename: Pseudonyms) -> Cell:
    raw = _text(value)
    if raw == "":
        return value
    if ";" in raw:  # a list of codes, e.g. alternative machines
        return ";".join(rename(kind, p.strip()) for p in raw.split(";") if p.strip())
    return rename(kind, raw)


def _read(path: Path, mapping: MappingSet) -> SourceTable:
    drop = personal_column_rule(mapping.personal_columns)
    if path.suffix == ".xlsx":
        from cip_connectors.excel import read_xlsx

        return read_xlsx(path, drop)
    return read_csv(path, mapping.delimiter, drop)


def _write(path: Path, header: list[str], rows: list[list[Cell]], mapping: MappingSet) -> None:
    if path.suffix == ".xlsx":
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        assert ws is not None
        ws.append(header)
        for row in rows:
            ws.append(row)
        wb.save(path)
        return
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, delimiter=mapping.delimiter, lineterminator="\n")
        writer.writerow(header)
        for row in rows:
            writer.writerow(
                [v.strftime(mapping.datetime_format) if isinstance(v, datetime) else v for v in row]
            )


def anonymised_mapping(mapping: MappingSet, rename: Pseudonyms) -> dict[str, object]:
    """The mapping for the anonymised files: code tables of pseudonymised columns map each
    pseudonym onto itself; every other code table (statuses, kinds) is kept."""
    kinds, _ = column_kinds(mapping)
    renamed: dict[str, str] = {}
    for table in mapping.tables:
        for rule in table.fields.values():
            if rule.code_table and rule.from_ and (table.source, rule.from_) in kinds:
                renamed[rule.code_table] = kinds[(table.source, rule.from_)]
    data = mapping.model_dump(by_alias=True, exclude_defaults=False)
    data["source_system"] = f"{mapping.source_system}-ANON"
    data["personal_columns"] = []
    data["code_tables"] = {
        name: _pseudonym_table(renamed[name], table, rename) if name in renamed else dict(table)
        for name, table in mapping.code_tables.items()
    }
    data["tables"] = [_table_dict(t) for t in mapping.tables]
    return data


def _pseudonym_table(kind: str, table: dict[str, str], rename: Pseudonyms) -> dict[str, str]:
    pseudonyms = sorted({rename(kind, src) for src in table})
    short = SHORT_CODES.get(kind)
    if short is None:
        return {p: p for p in pseudonyms}
    if len(pseudonyms) > 99:
        raise AnonymiseError(f"more than 99 codes for {short}; the standard layout allows 99")
    return {p: f"{short}-{i:02d}" for i, p in enumerate(pseudonyms, start=1)}


def _table_dict(table: TableMapping) -> dict[str, object]:
    fields = {
        name: rule.model_dump(by_alias=True, exclude_defaults=True)
        for name, rule in table.fields.items()
    }
    out: dict[str, object] = {"source": table.source, "target": table.target, "fields": fields}
    if table.unique:
        out["unique"] = True
    return out


def anonymise_export(
    export_dir: Path, mapping: MappingSet, out_dir: Path, key: bytes
) -> AnonymiseReport:
    """Write the anonymised export, its mapping and a report (no values) to ``out_dir``."""
    rename = Pseudonyms(key)
    kinds, read = column_kinds(mapping)
    report = AnonymiseReport()
    out_dir.mkdir(parents=True, exist_ok=True)
    sources = {t.source for t in mapping.tables}
    for extra in sorted(export_dir.iterdir()):
        if extra.is_file() and (extra.suffix not in (".csv", ".xlsx") or extra.stem not in sources):
            report.not_copied.append(extra.name)
    for source in sorted(sources):
        path = find_source(export_dir, source)
        if path is None:
            continue
        table = _read(path, mapping)
        keep = [c for c in table.header if c in read.get(source, set())]
        rows: list[list[Cell]] = []
        for _, row in table.rows:
            rows.append(
                [
                    _replace(row.get(c), kinds[(source, c)], rename)
                    if (source, c) in kinds
                    else row.get(c)
                    for c in keep
                ]
            )
        _write(out_dir / path.name, keep, rows, mapping)
        report.files[path.name] = FileReport(
            rows=len(rows),
            pseudonymised=[c for c in keep if (source, c) in kinds],
            kept=[c for c in keep if (source, c) not in kinds],
            dropped_personal=table.dropped_columns,
            dropped_unused=[c for c in table.header if c not in keep],
        )
    (out_dir / "mapping.yaml").write_text(
        "# Mapping for this anonymised export (made by scripts/anonymise_export.py).\n"
        + yaml.safe_dump(anonymised_mapping(mapping, rename), sort_keys=False, allow_unicode=True)
    )
    report.pseudonyms = rename.counts()
    (out_dir / "anonymise_report.json").write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n"
    )
    return report
