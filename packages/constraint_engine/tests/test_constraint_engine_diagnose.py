import json
from collections.abc import Callable
from pathlib import Path

import pytest

from constraint_engine.diagnose import main

PlantWriter = Callable[..., Path]


def test_text_summary(make_plant: PlantWriter, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(make_plant())]) == 0
    out = capsys.readouterr().out
    assert "Plant: Tiny" in out
    assert "Resources: 2" in out and "Products: 1" in out and "Orders: 1" in out
    assert "Event period: 2026-10-13T07:15:00+00:00 → 2026-10-13T09:50:00+00:00" in out
    assert "Missing files: none" in out


def test_json_summary_has_provenance(
    make_plant: PlantWriter, plant_files: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    bad_orders = plant_files["orders.csv"] + "SO-2,F-200,0,2026-10-20T16:00:00Z,open,,,\n"
    plant_dir = make_plant(skip=("events.csv",), extra={"orders.csv": bad_orders})
    main([str(plant_dir), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["counts"]["orders"]["formula_id"] == "record_count_v1"
    assert data["counts"]["orders"]["inputs"]["rejected_rows"] == 1
    assert data["missing_files"]["events.csv"]["reason"] == "file not found"
    assert data["event_period_start_at"] is None
    assert data["row_errors"][0]["line"] == 3


@pytest.mark.parametrize("section", ["detection", "forecast", "loss"])
def test_planned_sections_not_available_yet(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], section: str
) -> None:
    assert main([str(tmp_path), "--section", section]) == 0
    assert "not available yet" in capsys.readouterr().out
