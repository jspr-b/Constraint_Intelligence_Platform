"""Data quality backend on plant_a's ERP export: clean and with known injected defects."""

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cip_api.settings import Settings
from cip_api_testkit import World, make_client

pytestmark = pytest.mark.db
ERP = Path(__file__).resolve().parents[3] / "data" / "synthetic" / "plant_a" / "erp_export"


@pytest.fixture
def it(world: World, tmp_path: Path) -> TestClient:
    client = make_client(Settings(env="dev", data_dir=tmp_path, run_jobs_inline=True))
    body = {"tenant_id": str(world.a), "email": world.email("it")}
    assert client.post("/auth/dev-login", json=body).status_code == 204
    return client


def _import(client: TestClient, variant: str) -> None:
    files = [
        ("files", (f.name, f.read_bytes(), "text/csv"))
        for f in sorted((ERP / variant / "csv").iterdir())
    ]
    created = client.post("/plants/PLANT-1/imports", files=files).json()
    client.post(f"/imports/{created['import_id']}/run")


def test_nothing_imported_yet(it: TestClient) -> None:
    body = it.get("/plants/PLANT-1/data-quality").json()
    assert body["import_id"] is None and body["score"] is None and body["gaps"] == []


def test_defects_are_found_as_injected(it: TestClient) -> None:
    known = json.loads((ERP / "defects" / "defects.json").read_text())
    _import(it, "defects")
    body = it.get("/plants/PLANT-1/data-quality").json()
    assert body["score"]["formula_id"] == "data_quality_score_v1"
    assert 0 <= body["score"]["value"] < 100
    events = next(f for f in body["files"] if f["file"] == "events.csv")
    assert events["rejected"] == known["unknown_machine_code_rows"] and events["rows"] > 1000
    assert events["reasons"] == {"unknown": known["unknown_machine_code_rows"]}
    unpaired = sum(g["count"] for g in body["gaps"] if g["code"] == "unpaired_start")
    assert (
        known["missing_end_events"]
        <= unpaired
        <= (known["missing_end_events"] + known["unknown_machine_code_rows"])
    )
    assert any(g["code"] == "no_scrap" for g in body["gaps"]), "removed scrap shows as a gap"
    assert body["rows"]["formula_id"] == "record_count_v1"
    assert body["event_period_start_at"] < body["event_period_end_at"]
    assert body["event_period_weeks"]["formula_id"] == "event_period_weeks_v1"
    assert body["event_period_weeks"]["value"] >= 8, "plant_a covers the minimum history"


def test_clean_export_scores_higher(it: TestClient) -> None:
    _import(it, "defects")
    defects = it.get("/plants/PLANT-1/data-quality").json()["score"]["value"]
    _import(it, "clean")
    clean = it.get("/plants/PLANT-1/data-quality").json()
    assert clean["score"]["value"] > defects
    assert all(f["rejected"] == 0 for f in clean["files"])
    assert clean["files_missing"] == []


def test_other_plants_and_roles(sign_in: Callable[..., TestClient]) -> None:
    client = sign_in("coo")
    sign_in("coo").put(
        "/access/pages", json={"role": "shift_lead", "page": "data", "allowed": False}
    )
    assert client.get("/plants/PLANT-1/data-quality").status_code == 200
    assert sign_in("shift_lead").get("/plants/PLANT-1/data-quality").status_code == 403
