"""The generic mapping imports plant A's full ERP/MES export back into plant A."""

from datetime import datetime
from pathlib import Path

import pytest

from cip_connectors.importer import import_export
from cip_connectors.mapping import load_mapping
from constraint_engine.io.plant_loader import LoadedPlant, load_plant

ROOT = Path(__file__).resolve().parents[3]
PLANT_A = ROOT / "data" / "synthetic" / "plant_a"
MAPPING = ROOT / "packages" / "connectors" / "mappings" / "generic" / "mapping.yaml"
PLANT_INFO = {
    "plant_code": "PLANT-A",
    "name": "Plant A (synthetic)",
    "timezone_iana": "Europe/Amsterdam",
}


@pytest.fixture(scope="module", params=["csv", "xlsx"])
def imported(
    request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory
) -> LoadedPlant:
    out = tmp_path_factory.mktemp(request.param)
    report = import_export(
        PLANT_A / "erp_export" / "clean" / request.param, load_mapping(MAPPING), out, PLANT_INFO
    )
    assert (
        report.row_errors == [] and report.missing_required == [] and report.missing_sources == []
    )
    return load_plant(out)


@pytest.fixture(scope="module")
def original() -> LoadedPlant:
    return load_plant(PLANT_A)


def minute(record: object, *fields: str) -> tuple[object, ...]:
    out = []
    for name in fields:
        value = getattr(record, name)
        out.append(value.replace(second=0) if isinstance(value, datetime) else value)
    return tuple(out)


def test_imports_cleanly(imported: LoadedPlant) -> None:
    assert imported.row_errors == []
    assert set(imported.missing_files) == set()


@pytest.mark.parametrize(
    ("name", "fields"),
    [
        ("stations", ("station_code",)),
        ("resources", ("resource_code", "station_code")),
        (
            "products",
            (
                "sku",
                "family",
                "setup_family",
                "sales_price_eur_cents",
                "truly_variable_cost_eur_cents",
            ),
        ),
        (
            "orders",
            ("order_id", "sku", "quantity_units", "status", "due_at", "released_at", "shipped_at"),
        ),
        (
            "events",
            (
                "event_type",
                "at",
                "resource_code",
                "station_code",
                "order_id",
                "operation_seq",
                "down_reason_code",
            ),
        ),
        ("calendar", ("resource_code", "kind", "start_at", "end_at", "covered")),
        (
            "changeovers",
            ("resource_code", "from_setup_family", "to_setup_family", "changeover_min"),
        ),
        ("overtime", ("resource_code", "iso_year", "iso_week", "overtime_h")),
        ("capacity_costs", ("resource_code", "overtime_eur_cents_per_h", "extra_shift_eur_cents")),
        ("outsourcing", ("operation", "price_eur_cents_per_unit")),
    ],
)
def test_record_types_match_plant_a(
    imported: LoadedPlant, original: LoadedPlant, name: str, fields: tuple[str, ...]
) -> None:
    got = sorted((minute(r, *fields) for r in getattr(imported, name)), key=repr)
    want = sorted((minute(r, *fields) for r in getattr(original, name)), key=repr)
    assert got == want


def test_routings_match(imported: LoadedPlant, original: LoadedPlant) -> None:
    assert {r.sku: r.steps for r in imported.routings} == {
        r.sku: r.steps for r in original.routings
    }


def test_defect_export_through_import_and_quality_report(tmp_path: Path) -> None:
    """End to end: ERP defect fixture -> import -> load -> quality report."""
    import json

    from constraint_engine.io.plant_loader import RowError
    from constraint_engine.quality import quality_report

    defects_dir = PLANT_A / "erp_export" / "defects"
    known = json.loads((defects_dir / "defects.json").read_text())
    report = import_export(defects_dir / "csv", load_mapping(MAPPING), tmp_path, PLANT_INFO)
    import_errors = [RowError(e.file, e.line, e.reason) for e in report.row_errors]
    assert (
        sum("unknown code 'LAS9'" in e.reason for e in import_errors)
        == known["unknown_machine_code_rows"]
    )
    quality = quality_report(load_plant(tmp_path), import_errors)
    codes = {g.code for g in quality.gaps}
    assert {"unpaired_start", "no_scrap"} <= codes
    unpaired = sum(g.count for g in quality.gaps if g.code == "unpaired_start")
    # every removed end leaves one unpaired start; unknown-code rows can remove a few more
    assert (
        known["missing_end_events"]
        <= unpaired
        <= known["missing_end_events"] + known["unknown_machine_code_rows"]
    )
    assert isinstance(quality.score.value, int) and quality.score.value < 90
