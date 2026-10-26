"""Mapping wizard, column matching by rules (ADR-0011 §3, CI0005 seq 03).

The rules are checked on exports they were not written from: the four synthetic plants' own
exports against their hand-written mapping files.
"""

from pathlib import Path

import pytest
import yaml

from cip_connectors.wizard import recognise_export

ROOT = Path(__file__).resolve().parents[3]
PLANTS = [
    ("plant_a", "generic"),
    ("plant_b", "generic"),
    ("plant_c", "generic"),
    ("plant_d", "workshop_scans"),
]


def _fields(target: object) -> list[str]:
    if isinstance(target, str):
        return [target]
    if isinstance(target, list):
        return target
    if isinstance(target, dict):
        return list(target.values())
    return []


@pytest.mark.parametrize(("plant", "mapping"), PLANTS)
def test_rules_find_the_hand_written_mapping(plant: str, mapping: str) -> None:
    spec = yaml.safe_load(
        (ROOT / "packages/connectors/mappings" / mapping / "mapping.yaml").read_text()
    )
    found = recognise_export(
        sorted((ROOT / "data/synthetic" / plant / "erp_export/clean/csv").iterdir())
    )
    got = {(m.table.rsplit(".", 1)[0], m.column): m for m in found.columns}
    wrong = []
    for table in spec["tables"]:
        for name, f in table["fields"].items():
            if not isinstance(f, dict) or "from" not in f:
                continue
            m = got.get((table["source"], f["from"]))
            want = f"{table['target']}.{name}"
            if m is None or want not in _fields(m.target) or m.sure not in ("sure", "likely"):
                wrong.append((table["source"], f["from"], want, m and m.target))
    assert wrong == []


def _write(folder: Path, name: str, text: str) -> Path:
    path = folder / name
    path.write_text(text, encoding="utf-8")
    return path


STEPS = "Code;Omschrijving\nLAS1;Welding\nLAK1;Paint\nZAAG;Saw\n"


def _log(code_header: str, extra: str) -> str:
    rows = [f"{code_header};Tijdstip;Status;{extra}"]
    for i in range(60):
        code, status = ["LAS1", "LAK1", "ZAAG"][i % 3], ["GO", "END"][i % 2]
        rows.append(f"{code};2026-07-20 06:{i:02d};{status};{i % 7}")
    return "\n".join(rows) + "\n"


def test_content_alone_is_likely_and_a_name_alone_is_not_guessed(tmp_path: Path) -> None:
    # "Xq7" holds the step codes: matched from its content, to be checked by the client.
    # "Blub" holds numbers with a name that says nothing: asked, never guessed.
    files = [
        _write(tmp_path, "a.csv", STEPS),
        _write(tmp_path, "b.csv", _log("Xq7", "Blub")),
    ]
    found = recognise_export(files)
    by = {m.column: m for m in found.columns if m.table == "b.csv"}
    assert (by["Xq7"].target, by["Xq7"].sure) == ("events.resource_code", "likely")
    assert by["Xq7"].reasons == ["codes_of:steps"]
    assert (by["Tijdstip"].target, by["Tijdstip"].sure) == ("events.at", "sure")
    assert (by["Blub"].target, by["Blub"].sure) == (None, None)
    assert by["Blub"].reasons == ["not_matched"]


def test_personal_columns_are_listed_as_dropped_never_matched(tmp_path: Path) -> None:
    files = [
        _write(tmp_path, "a.csv", STEPS),
        _write(tmp_path, "b.csv", _log("Werkplek", "Medewerker")),
    ]
    found = recognise_export(files)
    personal = [m for m in found.columns if m.personal]
    assert [(m.table, m.column) for m in personal] == [("b.csv", "Medewerker")]
    assert "Medewerker" not in found.tables[1].header


def test_columns_follow_the_role_the_client_gave(tmp_path: Path) -> None:
    files = [
        _write(tmp_path, "a.csv", STEPS),
        _write(tmp_path, "b.csv", _log("Werkplek", "Aantal")),
    ]
    skipped = recognise_export(files, {"b.csv": "skip"})
    assert [m for m in skipped.columns if m.table == "b.csv"] == []
    assert skipped.role_of("b.csv").role is None  # type: ignore[union-attr]


def test_plant_a_demo_export_asks_nothing() -> None:
    # The demo must run straight after upload: every used column of plant A is sure.
    found = recognise_export(
        sorted((ROOT / "data/synthetic/plant_a/erp_export/clean/csv").iterdir())
    )
    asked = [
        (m.table, m.column, m.sure)
        for m in found.columns
        if not m.personal and m.sure in (None, "likely", "unsure")
    ]
    assert asked == []
