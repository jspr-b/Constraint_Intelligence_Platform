"""Import a directory of source exports into the standard plant layout."""

import csv
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from cip_connectors.convert import ConversionError, convert
from cip_connectors.mapping import MappingSet, TableMapping
from cip_connectors.readers import DropRule, SourceTable, find_source, read_csv

# Standard layout columns per target (packages/constraint_engine/docs/plant_layout.md).
STANDARD_COLUMNS: dict[str, tuple[str, ...]] = {
    "stations": ("station_code", "name"),
    "resources": ("resource_code", "name", "station_code", "kind", "parallel_units"),
    "products": (
        "sku",
        "name",
        "family",
        "setup_family",
        "sales_price_eur_cents",
        "truly_variable_cost_eur_cents",
    ),
    "routings": (
        "sku",
        "operation_seq",
        "operation",
        "resource_code",
        "alternative_resource_codes",
        "standard_setup_min",
        "standard_run_min_per_unit",
    ),
    "orders": (
        "order_id",
        "sku",
        "quantity_units",
        "due_at",
        "status",
        "released_at",
        "shipped_at",
        "material_ready_at",
        "order_value_eur_cents",
        "material_cost_eur_cents",
    ),
    "events": (
        "event_id",
        "event_type",
        "at",
        "resource_code",
        "station_code",
        "order_id",
        "operation_seq",
        "quantity_units",
        "scrap_units",
        "down_reason_code",
        "scrap_reason_code",
    ),
    "calendar": ("resource_code", "kind", "start_at", "end_at", "covered", "positions"),
    "resource_operations": ("resource_code", "operation", "standard_run_min_per_unit"),
    "changeovers": ("resource_code", "from_setup_family", "to_setup_family", "changeover_min"),
    "overtime": ("resource_code", "iso_year", "iso_week", "overtime_h"),
    "capacity_costs": ("resource_code", "overtime_eur_cents_per_h", "extra_shift_eur_cents"),
    "outsourcing": ("operation", "sku", "price_eur_cents_per_unit"),
    "teams": ("team_code", "name", "resource_codes"),
    "team_shifts": ("team_code", "start_at", "end_at", "positions"),
}
REQUIRED: dict[str, tuple[str, ...]] = {
    "stations": ("station_code", "name"),
    "resources": ("resource_code", "name", "station_code"),
    "products": ("sku", "name", "family", "sales_price_eur_cents", "truly_variable_cost_eur_cents"),
    "routings": ("sku", "operation_seq", "operation", "resource_code"),
    "orders": ("order_id", "quantity_units", "due_at"),
    "events": ("event_id", "event_type", "at"),
    "calendar": ("resource_code", "kind", "start_at", "end_at"),
    "resource_operations": ("resource_code", "operation"),
    "changeovers": ("resource_code", "from_setup_family", "to_setup_family", "changeover_min"),
    "overtime": ("resource_code", "iso_year", "iso_week", "overtime_h"),
    "capacity_costs": ("resource_code",),
    "outsourcing": ("operation", "price_eur_cents_per_unit"),
    "teams": ("team_code", "name", "resource_codes"),
    "team_shifts": ("team_code", "start_at", "end_at", "positions"),
}

Reader = Callable[[Path, MappingSet, DropRule], SourceTable]


@dataclass(frozen=True)
class ImportIssue:
    file: str
    line: int
    reason: str


@dataclass
class ImportReport:
    source_system: str
    rows_read: dict[str, int] = field(default_factory=dict)
    rows_written: dict[str, int] = field(default_factory=dict)
    row_errors: list[ImportIssue] = field(default_factory=list)
    dropped_columns: dict[str, list[str]] = field(default_factory=dict)
    missing_sources: list[str] = field(default_factory=list)
    missing_required: list[str] = field(default_factory=list)
    """``target.field`` entries a mapping does not cover; that target is not written."""

    def to_dict(self) -> dict[str, object]:
        return {
            "source_system": self.source_system,
            "rows_read": self.rows_read,
            "rows_written": self.rows_written,
            "row_errors": [vars(e) for e in self.row_errors],
            "dropped_columns": self.dropped_columns,
            "missing_sources": self.missing_sources,
            "missing_required": self.missing_required,
        }


def _default_reader(path: Path, mapping: MappingSet, drop: DropRule) -> SourceTable:
    if path.suffix == ".xlsx":
        from cip_connectors.excel import read_xlsx

        return read_xlsx(path, drop)
    return read_csv(path, mapping.delimiter, drop)


def _map_table(
    table: TableMapping, source: SourceTable, mapping: MappingSet, report: ImportReport
) -> list[dict[str, str]] | None:
    missing = [f for f in REQUIRED[table.target] if f not in table.fields]
    missing += [
        f
        for f, rule in table.fields.items()
        if rule.from_ is not None and rule.from_ not in source.header and not rule.optional
    ]
    if missing:
        report.missing_required += [f"{table.target}.{f}" for f in missing]
        return None
    out: list[dict[str, str]] = []
    for line, row in source.rows:
        record: dict[str, str] = {}
        try:
            for name, rule in table.fields.items():
                if rule.generate == "row_id":
                    value: str | None = f"{rule.prefix}{source.name}-{line}"
                elif rule.constant is not None:
                    value = rule.constant
                else:
                    assert rule.from_ is not None
                    value = convert(row.get(rule.from_), rule, mapping, rule.from_)
                if value is not None:
                    record[name] = value
        except ConversionError as exc:
            report.row_errors.append(ImportIssue(source.path.name, line, str(exc)))
            continue
        out.append(record)
    return out


def _write(path: Path, target: str, rows: list[dict[str, str]]) -> None:
    columns = STANDARD_COLUMNS[target]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def import_export(
    export_dir: Path | str,
    mapping: MappingSet,
    out_dir: Path | str,
    plant: dict[str, str] | None = None,
    drop: DropRule | None = None,
    reader: Reader = _default_reader,
) -> ImportReport:
    """Map every source table in ``export_dir`` and write the standard layout to ``out_dir``."""
    from cip_connectors.privacy import personal_column_rule

    src, out = Path(export_dir), Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    drop_rule = drop or personal_column_rule(mapping.personal_columns)
    report = ImportReport(mapping.source_system)
    written: dict[str, list[dict[str, str]]] = {}
    for table in mapping.tables:
        path = find_source(src, table.source)
        if path is None:
            report.missing_sources.append(table.source)
            continue
        source = reader(path, mapping, drop_rule)
        report.rows_read[table.source] = len(source.rows)
        if source.dropped_columns:
            report.dropped_columns[table.source] = source.dropped_columns
        rows = _map_table(table, source, mapping, report)
        if rows is None:
            continue
        if table.unique:
            rows = [dict(t) for t in dict.fromkeys(tuple(r.items()) for r in rows)]
        written.setdefault(table.target, []).extend(rows)
    for target, rows in written.items():
        _write(out / f"{target}.csv", target, rows)
        report.rows_written[target] = len(rows)
    if plant is not None:
        (out / "plant.json").write_text(json.dumps(plant, indent=2) + "\n")
    (out / "import_report.json").write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n"
    )
    return report
