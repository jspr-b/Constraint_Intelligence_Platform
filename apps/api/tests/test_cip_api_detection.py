"""Constraint detection: saved by the facts job per period, read with every method's evidence."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from cip_api.detection import gap_impacts
from cip_api.settings import Settings
from cip_api_testkit import World, make_client
from constraint_engine.figure import Confidence

pytestmark = pytest.mark.db
EXPORT = Path(__file__).resolve().parents[3] / "data" / "synthetic" / "plant_a" / "erp_export"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(env="dev", data_dir=tmp_path, run_jobs_inline=True)


def _login(world: World, settings: Settings, role: str, tenant: str = "a") -> TestClient:
    client = make_client(settings)
    body = {"tenant_id": str(getattr(world, tenant)), "email": world.email(role, tenant)}
    assert client.post("/auth/dev-login", json=body).status_code == 204
    return client


def _import(it: TestClient) -> str:
    folder = EXPORT / "clean" / "csv"
    files = [("files", (f.name, f.read_bytes(), "text/csv")) for f in sorted(folder.iterdir())]
    body = it.post("/plants/PLANT-1/imports", files=files).json()
    assert it.post(f"/imports/{body['import_id']}/run").status_code == 202
    return str(body["import_id"])


def test_an_import_saves_the_constraint_per_period(world: World, settings: Settings) -> None:
    it = _login(world, settings, "it")
    import_id = _import(it)
    whole = it.get("/plants/PLANT-1/detection").json()
    assert whole["import_id"] == import_id and whole["run"]["status"] == "ready"
    (d,) = whole["detections"]
    assert (d["resource_code"], d["kind"], d["confidence"]) == ("PNT-01", "internal", "high")
    assert d["agreement"]["formula_id"] == "constraint_agreement_pct_v1"
    assert d["agreement"]["value"] == 100
    assert {m["method"] for m in d["methods"]} == {
        "utilisation",
        "queue",
        "active_period",
        "starved_blocked",
    }
    assert all(m["evidence"]["formula_id"] for m in d["methods"])
    assert d["reasons"][0]["code"] == "methods_agree"
    months = it.get("/plants/PLANT-1/detection", params={"period_kind": "month"}).json()
    weeks = it.get("/plants/PLANT-1/detection", params={"period_kind": "week"}).json()
    assert len(months["detections"]) >= 3 and len(weeks["detections"]) >= 10
    first = months["detections"][0]
    one = it.get(
        "/plants/PLANT-1/detection",
        params={"period_kind": "month", "period_start_at": first["period_start_at"]},
    ).json()
    assert [x["period_start_at"] for x in one["detections"]] == [first["period_start_at"]]


def test_a_new_import_replaces_the_detections(world: World, settings: Settings) -> None:
    it = _login(world, settings, "it")
    _import(it)
    second = _import(it)
    with world.owner.connect() as conn:
        ids = conn.execute(
            text("SELECT DISTINCT import_id FROM detections WHERE tenant_id = :t"),
            {"t": world.a},
        ).all()
    assert [str(r[0]) for r in ids] == [second]


def test_before_any_import_there_is_no_detection(world: World, settings: Settings) -> None:
    body = _login(world, settings, "it").get("/plants/PLANT-1/detection").json()
    assert body == {"plant_code": "PLANT-1", "run": None, "import_id": None, "detections": []}


def test_other_tenants_see_nothing(world: World, settings: Settings) -> None:
    _import(_login(world, settings, "it"))
    other = _login(world, settings, "it", "b")
    body = other.get("/plants/PLANT-1/detection").json()  # tenant B has its own PLANT-1
    assert body["detections"] == [] and body["run"] is None


def test_gap_impacts_read_the_quality_report() -> None:
    report = '{"quality": {"gaps": [{"confidence_impact": "high"}, {"confidence_impact": "x"}]}}'
    assert gap_impacts(report) == [Confidence.HIGH]
    assert gap_impacts(None) == []
