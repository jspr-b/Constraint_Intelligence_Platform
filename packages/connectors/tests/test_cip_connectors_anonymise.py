"""Anonymising plant A's export: no names, codes or personal columns left, same answer."""

from pathlib import Path

import pytest

from cip_connectors.anonymise import AnonymiseError, Pseudonyms, anonymise_export
from cip_connectors.importer import import_export
from cip_connectors.mapping import load_mapping
from constraint_engine.detection import detect_periods
from constraint_engine.facts import measured_facts
from constraint_engine.io.plant_loader import load_plant

ROOT = Path(__file__).resolve().parents[3]
EXPORT = ROOT / "data" / "synthetic" / "plant_a" / "erp_export" / "clean"
MAPPING = load_mapping(ROOT / "packages" / "connectors" / "mappings" / "generic" / "mapping.yaml")
KEY = bytes(range(32))
PLANT = {"plant_code": "PLANT-A", "name": "Plant A", "timezone_iana": "Europe/Amsterdam"}
# Values from the original export that must not survive anonymisation.
ORIGINAL = ["LAK1", "SNIJ1", "Laser cutting", "Welding cell", "B-40", "Bracket set", "RAL9005"]


def _all_text(folder: Path) -> str:
    return "\n".join(p.read_text(errors="ignore") for p in folder.iterdir() if p.suffix == ".csv")


@pytest.mark.parametrize("kind", ["csv", "xlsx"])
def test_anonymised_export_keeps_no_names_codes_or_people(kind: str, tmp_path: Path) -> None:
    out = tmp_path / "anon"
    report = anonymise_export(EXPORT / kind, MAPPING, out, KEY)
    assert report.files["mes_events." + kind].dropped_personal == ["Medewerker"]
    assert "Werkplek" in report.files["werkplekken." + kind].pseudonymised
    assert "Tijdstip" in report.files["mes_events." + kind].kept
    if kind == "csv":
        text = _all_text(out)
        for value in [*ORIGINAL, "MEDEWERKER"]:
            assert value not in text, value
    mapping_text = (out / "mapping.yaml").read_text()
    for value in ORIGINAL[:4]:
        assert value not in mapping_text, value


def test_anonymised_export_imports_and_gives_the_same_answer(tmp_path: Path) -> None:
    anon = tmp_path / "anon"
    anonymise_export(EXPORT / "csv", MAPPING, anon, KEY)
    original = import_export(EXPORT / "csv", MAPPING, tmp_path / "orig_std", PLANT)
    imported = import_export(
        anon, load_mapping(anon / "mapping.yaml"), tmp_path / "anon_std", PLANT
    )
    assert imported.row_errors == [] and imported.missing_required == []
    assert imported.rows_written == original.rows_written

    def answer(folder: Path) -> list[tuple[str, str | None, str]]:
        plant = load_plant(folder)
        return [
            (kind, d.resource_code, d.confidence.label)
            for kind, d in detect_periods(plant, measured_facts(plant), kinds=("all",))
        ]

    before, after = answer(tmp_path / "orig_std"), answer(tmp_path / "anon_std")
    paint = load_mapping(anon / "mapping.yaml").code_tables["resource"][
        Pseudonyms(KEY)("RES", "LAK1")
    ]
    assert paint.startswith("MCH-")
    assert before[0][1] == "PNT-01"
    assert after == [(k, paint if code == "PNT-01" else code, c) for k, code, c in before]


def test_same_key_same_pseudonyms_other_key_others(tmp_path: Path) -> None:
    anonymise_export(EXPORT / "csv", MAPPING, tmp_path / "a", KEY)
    anonymise_export(EXPORT / "csv", MAPPING, tmp_path / "b", KEY)
    anonymise_export(EXPORT / "csv", MAPPING, tmp_path / "c", bytes(range(1, 33)))
    orders = "orders.csv"
    assert (tmp_path / "a" / orders).read_text() == (tmp_path / "b" / orders).read_text()
    assert (tmp_path / "a" / orders).read_text() != (tmp_path / "c" / orders).read_text()


def test_short_key_is_refused() -> None:
    with pytest.raises(AnonymiseError):
        Pseudonyms(b"short")


def test_files_the_mapping_does_not_read_are_not_copied(tmp_path: Path) -> None:
    export = tmp_path / "export"
    export.mkdir()
    for f in (EXPORT / "csv").iterdir():
        (export / f.name).write_bytes(f.read_bytes())
    (export / "salaries.csv").write_text("Name;Salary\nA;1\n")
    report = anonymise_export(export, MAPPING, tmp_path / "out", KEY)
    assert report.not_copied == ["salaries.csv"]
    assert not (tmp_path / "out" / "salaries.csv").exists()
