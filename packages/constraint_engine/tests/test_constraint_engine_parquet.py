"""Parquet round trip and DuckDB queries on plant A."""

from collections import Counter
from pathlib import Path

import duckdb
import pytest

from constraint_engine.diagnose import main
from constraint_engine.io.parquet import RECORDS, from_parquet, to_parquet
from constraint_engine.io.plant_loader import LoadedPlant, load_plant

PLANT_A = Path(__file__).resolve().parents[3] / "data" / "synthetic" / "plant_a"


@pytest.fixture(scope="module")
def plant() -> LoadedPlant:
    return load_plant(PLANT_A)


def test_round_trip_is_exact(plant: LoadedPlant, tmp_path: Path) -> None:
    back = from_parquet(to_parquet(plant, tmp_path / "pq"))
    assert back.plant == plant.plant
    for name in RECORDS:
        assert getattr(back, name) == getattr(plant, name), name
    assert sorted(back.routings, key=lambda r: r.sku) == sorted(plant.routings, key=lambda r: r.sku)
    assert back.row_errors == plant.row_errors
    assert back.missing_files == plant.missing_files


def test_duckdb_counts_events_per_machine(plant: LoadedPlant, tmp_path: Path) -> None:
    out = to_parquet(plant, tmp_path / "pq")
    rows = duckdb.sql(
        f"SELECT resource_code, count(*) FROM '{out / 'events.parquet'}' "
        "WHERE resource_code IS NOT NULL GROUP BY 1"
    ).fetchall()
    expected = Counter(e.resource_code for e in plant.events if e.resource_code)
    assert dict(rows) == dict(expected)


def test_cli_writes_parquet(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(PLANT_A), "--parquet-out", str(tmp_path / "pq")]) == 0
    assert (tmp_path / "pq" / "events.parquet").exists()
    assert "Plant: Plant A" in capsys.readouterr().out
