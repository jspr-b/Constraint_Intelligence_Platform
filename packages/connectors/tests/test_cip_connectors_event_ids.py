"""The same event gets the same id in every upload (ADR-0010), whatever the file name or line.

Known answer fixed before the code: today's mappings generate `<file>-<line>`, so this is a strict
xfail until CI0004 sequence 02 stores ids made from the event itself.
"""

from pathlib import Path

import pytest

from cip_connectors.importer import import_export
from cip_connectors.mapping import load_mapping
from constraint_engine.io.plant_loader import LoadedPlant, load_plant

ROOT = Path(__file__).resolve().parents[3]
CASES = ROOT / "data" / "synthetic" / "import_cases"
CLEAN = ROOT / "data" / "synthetic" / "plant_a" / "erp_export" / "clean" / "csv"
MAPPING = ROOT / "packages" / "connectors" / "mappings" / "generic" / "mapping.yaml"
PLANT_INFO = {
    "plant_code": "PLANT-A",
    "name": "Plant A (synthetic)",
    "timezone_iana": "Europe/Amsterdam",
}


def _load(source: Path, out: Path) -> LoadedPlant:
    import_export(source, load_mapping(MAPPING), out, PLANT_INFO)
    return load_plant(out)


def _key(e: object) -> tuple[object, ...]:
    return tuple(getattr(e, f) for f in ("resource_code", "order_id", "event_type", "at"))


@pytest.mark.xfail(strict=True, reason="ADR-0010: ids from the event itself, CI0004 seq 02")
def test_an_event_keeps_its_id_in_a_file_cut_differently(tmp_path: Path) -> None:
    whole = _load(CLEAN, tmp_path / "whole")
    again = _load(CASES / "repeat" / "upload_2", tmp_path / "again")
    ids = {_key(e): e.event_id for e in whole.events}
    assert len(ids) == len(whole.events)  # the content identifies each event in plant A
    assert again.events and all(ids[_key(e)] == e.event_id for e in again.events)


@pytest.mark.xfail(strict=True, reason="ADR-0010: ids from the event itself, CI0004 seq 02")
def test_different_events_in_files_with_the_same_name_get_different_ids(tmp_path: Path) -> None:
    first = _load(CASES / "split" / "upload_1", tmp_path / "first")
    second = _load(CASES / "split" / "upload_2", tmp_path / "second")
    assert not {e.event_id for e in first.events} & {e.event_id for e in second.events}
