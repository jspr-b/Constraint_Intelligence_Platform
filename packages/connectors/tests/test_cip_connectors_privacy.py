"""Personal data never enters the platform."""

import json
import logging
from pathlib import Path

import pytest

from cip_connectors.importer import import_export
from cip_connectors.mapping import load_mapping
from cip_connectors.privacy import is_personal

ROOT = Path(__file__).resolve().parents[3]
MAPPING = ROOT / "packages" / "connectors" / "mappings" / "generic" / "mapping.yaml"
SECRET = "Jan-de-Vries-TEST"


@pytest.mark.parametrize(
    "column",
    [
        "Medewerker",
        "Medewerkernummer",
        "Operator",
        "employee_id",
        "Badge nr",
        "Voornaam",
        "E-mail",
        "Personeelsnummer",
        "Gebruikersnaam",
        "Worker",
        "Telefoon",
    ],
)
def test_denylist_catches_person_columns(column: str) -> None:
    assert is_personal(column)


@pytest.mark.parametrize(
    "column", ["Werkplek", "Bon", "Omschrijving", "Afdeling", "Status", "Aantal", "Artikel"]
)
def test_plant_columns_are_kept(column: str) -> None:
    assert not is_personal(column)


def test_mapping_can_mark_extra_columns() -> None:
    assert is_personal("Ploegleider", frozenset({"ploegleider"}))


def write_events(path: Path, value: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "mes_events.csv").write_text(
        "Werkplek;Afdeling;Bon;Bewerking;Status;Tijdstip;Aantal;Afkeur;Storingscode;Afkeurcode;Medewerker;Operator\n"
        f"LAS2;;24187;020;GESTART;13-10-2026 09:15;14;;;;{value};{value}\n"
        f"LAS9;;24188;020;GESTART;niet-een-datum;14;;;;{value};{value}\n"
    )


def test_personal_values_never_reach_output_report_logs_or_errors(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    write_events(tmp_path / "src", SECRET)
    caplog.set_level(logging.DEBUG)
    report = import_export(tmp_path / "src", load_mapping(MAPPING), tmp_path / "out")
    assert report.dropped_columns == {"mes_events": ["Medewerker", "Operator"]}
    assert len(report.row_errors) == 1  # the bad row is reported...
    texts = [p.read_text() for p in (tmp_path / "out").iterdir()]
    texts += [json.dumps(report.to_dict()), caplog.text, *(e.reason for e in report.row_errors)]
    assert all(SECRET not in t for t in texts)  # ...without the personal value


def test_fixture_employee_column_is_dropped_on_full_import(tmp_path: Path) -> None:
    src = ROOT / "data" / "synthetic" / "plant_a" / "erp_export" / "clean" / "csv"
    import_export(src, load_mapping(MAPPING), tmp_path)
    assert all("TEST-MEDEWERKER" not in p.read_text() for p in tmp_path.iterdir())
