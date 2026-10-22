"""Bottleneck loss: saved with the facts after each import, read with full provenance."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cip_api.settings import Settings
from cip_api_testkit import World, make_client

pytestmark = pytest.mark.db
DATA = Path(__file__).resolve().parents[3] / "data" / "synthetic"
CAUSES = {"breakdowns", "setup", "starved", "blocked", "breaks", "maintenance", "scrap", "total"}


@pytest.fixture
def it(world: World, tmp_path: Path) -> TestClient:
    client = make_client(Settings(env="dev", data_dir=tmp_path, run_jobs_inline=True))
    body = {"tenant_id": str(world.a), "email": world.email("it")}
    assert client.post("/auth/dev-login", json=body).status_code == 204
    return client


def _import(it: TestClient, plant: str) -> None:
    folder = DATA / plant / "erp_export" / "clean" / "csv"
    files = [("files", (f.name, f.read_bytes(), "text/csv")) for f in sorted(folder.iterdir())]
    body = it.post("/plants/PLANT-1/imports", files=files).json()
    assert it.post(f"/imports/{body['import_id']}/run").status_code == 202


def _facts(it: TestClient, family: str, kind: str = "all") -> list[dict]:  # type: ignore[type-arg]
    params = {"family": [family], "period_kind": kind}
    facts: list[dict] = it.get("/plants/PLANT-1/facts", params=params).json()["facts"]  # type: ignore[type-arg]
    return facts


def test_an_import_saves_the_bottleneck_loss_in_hours_and_euros(it: TestClient) -> None:
    _import(it, "plant_a")
    loss = _facts(it, "loss")
    hours = {f["reason_code"]: f["figure"] for f in loss if f["measure"] == "lost_h"}
    euros = {f["reason_code"]: f["figure"] for f in loss if f["measure"] == "lost_eur_cents"}
    assert set(hours) == set(euros) == CAUSES
    assert {f["resource_code"] for f in loss} == {"PNT-01"}
    total = euros["total"]
    assert isinstance(total["value"], int) and total["value"] > 0
    assert total["formula_id"] == "lost_throughput_eur_cents_v1"
    assert total["inputs"]["lost_h"]["formula_id"] == "lost_constraint_h_total_v1"
    rate = total["inputs"]["throughput_per_constraint_h_eur_cents"]
    assert (
        rate["formula_id"] == "throughput_per_constraint_h_v1" and rate["unit"] == "eur_cents_per_h"
    )
    assert hours["breaks"]["value"] == pytest.approx(90.0, abs=0.1)
    months = _facts(it, "loss", "month")
    assert len({f["figure"]["period_start_at"] for f in months}) == 4
    rates = _facts(it, "throughput")
    assert {f["reason_code"] for f in rates} == {None, "B-40", "C-3", "F-200", "H-12"}


def test_a_plant_without_a_bottleneck_has_no_loss_and_says_why(it: TestClient) -> None:
    _import(it, "plant_b")
    assert _facts(it, "loss") == []
    (d,) = it.get("/plants/PLANT-1/detection").json()["detections"]
    assert d["kind"] == "market" and d["reasons"][0]["code"] == "no_machine_binding"


def test_a_role_set_to_hours_sees_no_euros(world: World, it: TestClient, tmp_path: Path) -> None:
    from sqlalchemy import text

    _import(it, "plant_a")
    with world.owner.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO access_data (tenant_id, role, money, plants) "
                "VALUES (:t, 'planner', 'hours', 'all')"
            ),
            {"t": world.a},
        )
    planner = make_client(Settings(env="dev", data_dir=tmp_path, run_jobs_inline=True))
    body = {"tenant_id": str(world.a), "email": world.email("planner")}
    assert planner.post("/auth/dev-login", json=body).status_code == 204
    loss = _facts(planner, "loss")
    euros = [f["figure"] for f in loss if f["measure"] == "lost_eur_cents"]
    assert euros and all(
        f["unit"] == "h" and f["formula_id"] == "constraint_hours_v1" for f in euros
    )
    total = next(
        f["figure"] for f in loss if f["measure"] == "lost_h" and f["reason_code"] == "total"
    )
    shown = next(
        f["figure"]
        for f in loss
        if f["measure"] == "lost_eur_cents" and f["reason_code"] == "total"
    )
    assert shown["value"] == pytest.approx(total["value"], rel=1e-3)
    assert _facts(planner, "throughput") == []
