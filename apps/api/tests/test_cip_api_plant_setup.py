"""Plant setup page backend: kick-off entry, edits by role, engine numbers after an import."""

from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from cip_api.settings import Settings
from cip_api_testkit import World, make_client

pytestmark = pytest.mark.db
EXPORT = Path(__file__).resolve().parents[3] / "data" / "synthetic" / "plant_a" / "erp_export"


@pytest.fixture
def client_as(world: World, tmp_path: Path) -> Callable[[str], TestClient]:
    settings = Settings(env="dev", data_dir=tmp_path, run_jobs_inline=True)

    def _client(role: str) -> TestClient:
        client = make_client(settings)
        body = {"tenant_id": str(world.a), "email": world.email(role)}
        assert client.post("/auth/dev-login", json=body).status_code == 204
        return client

    return _client


def test_kick_off_entry_of_plant_stations_and_machines(
    world: World, client_as: Callable[[str], TestClient]
) -> None:
    planner = client_as("planner")
    plant = {"plant_code": "plant-k", "name": "Kick-off plant", "timezone_iana": "Europe/Amsterdam"}
    created = planner.post("/plants", json=plant)
    assert created.status_code == 201 and created.json()["plant_code"] == "PLANT-K"
    assert planner.post("/plants", json=plant).status_code == 409
    assert (
        planner.post(
            "/plants", json=plant | {"plant_code": "B", "timezone_iana": "Mars/Base"}
        ).status_code
        == 422
    )
    planner.put("/plants/PLANT-K/stations/paint", json={"name": "Paint"})
    body = planner.put(
        "/plants/PLANT-K/resources/pnt-01",
        json={"name": "Paint line", "station_code": "PAINT", "parallel_units": 1},
    ).json()
    assert body["stations"] == [
        {
            "station_code": "PAINT",
            "name": "Paint",
            "machines": [
                {
                    "resource_code": "PNT-01",
                    "name": "Paint line",
                    "kind": "machine",
                    "parallel_units": 1,
                    "has_station_login": False,
                }
            ],
        }
    ]
    bad = {"name": "X", "station_code": "NOWHERE"}
    assert planner.put("/plants/PLANT-K/resources/X-1", json=bad).status_code == 422
    bench = {"name": "Hand welding", "station_code": "PAINT", "parallel_units": 3}
    assert planner.put("/plants/PLANT-K/resources/weld-bench", json=bench).status_code == 200
    for code in ["OPERATOR-1", "WELD_1", "1ST"]:
        refused = planner.put(f"/plants/PLANT-K/resources/{code}", json=bench)
        assert refused.status_code == 422 and refused.json()["code"] == "bad_step_code"
    with world.owner.connect() as conn:
        actions = (
            conn.execute(
                text("SELECT action FROM audit_log WHERE tenant_id = :t ORDER BY id"),
                {"t": world.a},
            )
            .scalars()
            .all()
        )
    assert {"plant_created", "station_saved", "machine_saved"} <= set(actions)


@pytest.mark.parametrize("role", ["plant_director", "coo", "shift_lead"])
def test_roles_without_the_setup_decision_only_read(
    role: str, client_as: Callable[[str], TestClient]
) -> None:
    client = client_as(role)
    assert client.get("/plants/PLANT-1/setup").status_code == 200
    assert client.put("/plants/PLANT-1/stations/X", json={"name": "X"}).status_code == 403
    plant = {"plant_code": "NOPE", "name": "No"}
    assert client.post("/plants", json=plant).status_code == 403


def test_a_machine_with_a_station_login_is_not_deleted(
    client_as: Callable[[str], TestClient],
) -> None:
    it = client_as("it")
    assert it.delete("/plants/PLANT-1/resources/PNT-01").status_code == 409


def test_engine_numbers_after_an_import(client_as: Callable[[str], TestClient]) -> None:
    it = client_as("it")
    files = [
        ("files", (f.name, f.read_bytes(), "text/csv"))
        for f in sorted((EXPORT / "clean" / "csv").iterdir())
    ]
    created = it.post("/plants/PLANT-1/imports", files=files).json()
    it.post(f"/imports/{created['import_id']}/run")
    body = it.get("/plants/PLANT-1/setup").json()
    assert body["measured_from_import"] == created["import_id"]
    measured = [o for o in body["operations"] if o["measured_min_per_unit"]]
    assert measured, "measured times come from the import's reconstruction"
    assert all(o["measured_min_per_unit"]["formula_id"] == "task_time_median_v1" for o in measured)
    assert any(o["erp_min_per_unit"] is not None for o in body["operations"])
    products = body["products"]
    assert products and all(
        p["throughput_per_unit"]["formula_id"] == "throughput_per_unit_v1"
        and p["throughput_per_unit"]["value"]
        == p["sales_price_eur_cents"] - p["truly_variable_cost_eur_cents"]
        for p in products
    )
    it.put(
        "/plants/PLANT-1/changeovers",
        json={
            "resource_code": "PNT-01",
            "from_setup_family": "RAL7016",
            "to_setup_family": "RAL9005",
            "changeover_min": 45,
        },
    )
    body = it.put(
        "/plants/PLANT-1/capacity-costs/PNT-01",
        json={"overtime_eur_cents_per_h": 6250, "extra_shift_eur_cents": 250000},
    ).json()
    assert {
        "resource_code": "PNT-01",
        "from_setup_family": "RAL7016",
        "to_setup_family": "RAL9005",
        "changeover_min": 45.0,
    } in body["changeovers"]
    assert {
        "resource_code": "PNT-01",
        "overtime_eur_cents_per_h": 6250,
        "extra_shift_eur_cents": 250000,
    } in body["capacity_costs"]
