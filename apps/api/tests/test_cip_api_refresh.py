"""Automatic refresh (ADR-0010 point 10): every data change recalculates the plant's numbers,
the old numbers stay until the new ones are ready, and a failed or stuck run is reported and
can be retried."""

import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from cip_api import facts as facts_module
from cip_api.auth.sessions import tenant_conn
from cip_api.settings import Settings
from cip_api_testkit import World, make_client

pytestmark = pytest.mark.db
CLEAN = Path(__file__).resolve().parents[3] / "data" / "synthetic" / "plant_a" / "erp_export"
MAINTENANCE = {
    "resource_code": "PNT-01",
    "kind": "maintenance",
    "start_at": "2026-07-21T08:00:00Z",
    "end_at": "2026-07-21T10:00:00Z",
}


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(env="dev", data_dir=tmp_path, run_jobs_inline=True)


def _client(world: World, settings: Settings, role: str) -> TestClient:
    client = make_client(settings)
    body = {"tenant_id": str(world.a), "email": world.email(role)}
    assert client.post("/auth/dev-login", json=body).status_code == 204
    return client


@pytest.fixture
def it(world: World, settings: Settings) -> TestClient:
    return _client(world, settings, "it")


def _import(it: TestClient) -> str:
    folder = CLEAN / "clean" / "csv"
    files = [("files", (f.name, f.read_bytes(), "text/csv")) for f in sorted(folder.iterdir())]
    body = it.post("/plants/PLANT-1/imports", files=files).json()
    assert it.post(f"/imports/{body['import_id']}/run").status_code == 202
    return str(body["import_id"])


def _run(world: World) -> Any:
    with world.owner.connect() as conn:
        return conn.execute(
            text(
                "SELECT status, reason, requested_gen, done_gen, finished_at FROM fact_runs "
                "WHERE tenant_id = :t AND plant_code = 'PLANT-1'"
            ),
            {"t": world.a},
        ).one()


def _status(client: TestClient) -> dict[str, Any]:
    found: dict[str, Any] = next(
        p for p in client.get("/refresh-status").json() if p["plant_code"] == "PLANT-1"
    )
    return found


def test_a_plant_without_an_import_has_nothing_to_refresh(world: World, settings: Settings) -> None:
    planner = _client(world, settings, "planner")
    assert planner.post("/plants/PLANT-1/calendar/windows", json=MAINTENANCE).status_code == 201
    status = _status(planner)
    assert status["status"] == "none" and status["numbers_at"] is None
    retry = _client(world, settings, "it").post("/plants/PLANT-1/refresh")
    assert retry.status_code == 409 and retry.json()["code"] == "refresh_needs_import"


def test_a_calendar_edit_recalculates_without_a_button(
    world: World, it: TestClient, settings: Settings
) -> None:
    _import(it)
    before = _run(world)
    assert (before.status, before.reason) == ("ready", "import")
    planner = _client(world, settings, "planner")
    assert planner.post("/plants/PLANT-1/calendar/windows", json=MAINTENANCE).status_code == 201
    after = _run(world)
    assert (after.status, after.reason) == ("ready", "calendar")
    assert after.requested_gen == after.done_gen == before.requested_gen + 1
    assert after.finished_at > before.finished_at
    director = _client(world, settings, "plant_director")
    seen = _status(director)
    assert (seen["status"], seen["reason"], seen["problem"]) == ("ready", "calendar", None)
    assert seen["last_event_at"] and seen["data_age_days"] is not None
    assert seen["old_after_days"] == settings.data_old_after_days


def test_an_overtime_edit_recalculates(world: World, it: TestClient) -> None:
    _import(it)
    gen = _run(world).requested_gen
    body = {"resource_code": "PNT-01", "iso_year": 2026, "iso_week": 30, "overtime_h": 4}
    assert it.put("/plants/PLANT-1/overtime", json=body).status_code == 200
    run = _run(world)
    assert (run.reason, run.requested_gen) == ("calendar", gen + 1)


def test_the_old_numbers_stay_while_recalculating(
    world: World, it: TestClient, settings: Settings
) -> None:
    import_id = uuid.UUID(_import(it))
    numbers_at = _status(it)["numbers_at"]
    with tenant_conn(settings, world.a) as conn:
        facts_module.start_facts(conn, world.a, "PLANT-1", import_id, "calendar")
    status = _status(it)
    assert (status["status"], status["reason"]) == ("calculating", "calendar")
    assert status["numbers_at"] == numbers_at, "the numbers shown are still the old ones"
    shown = it.get("/plants/PLANT-1/facts").json()
    assert shown["run"]["status"] == "calculating"
    assert shown["facts"], "the pages keep the previous answer"


def test_changes_during_a_calculation_are_not_lost(
    world: World, it: TestClient, settings: Settings
) -> None:
    import_id = uuid.UUID(_import(it))
    with tenant_conn(settings, world.a) as conn:
        facts_module.start_facts(conn, world.a, "PLANT-1", import_id, "fix")
    first = _run(world).requested_gen
    with tenant_conn(settings, world.a) as conn:  # a second change while the first runs
        facts_module.start_facts(conn, world.a, "PLANT-1", import_id, "calendar")
    facts_module.compute_facts(settings, world.a, import_id, gen=first)
    run = _run(world)
    assert run.status == "calculating" and run.done_gen == first, "the newer change waits"
    facts_module.refresh_plant(settings, world.a, import_id)
    run = _run(world)
    assert run.status == "ready" and run.done_gen == run.requested_gen == first + 1


def test_a_stuck_calculation_is_reported_and_retried(
    world: World, it: TestClient, settings: Settings
) -> None:
    _import(it)
    with world.owner.begin() as conn:
        conn.execute(
            text(
                "UPDATE fact_runs SET status = 'calculating', requested_gen = requested_gen + 1, "
                "requested_at = now() - interval '1 hour' WHERE tenant_id = :t"
            ),
            {"t": world.a},
        )
    status = _status(it)
    assert (status["status"], status["problem"]) == ("failed", "did_not_finish")
    assert status["numbers_at"], "the old numbers stay, marked as older"
    director = _client(world, settings, "plant_director")
    assert director.post("/plants/PLANT-1/refresh").status_code == 403
    retried = it.post("/plants/PLANT-1/refresh")
    assert retried.status_code == 202, retried.text
    assert _status(it)["status"] == "ready" and _run(world).reason == "retry"
    with world.owner.connect() as conn:
        audited = conn.execute(
            text(
                "SELECT count(*) FROM audit_log WHERE tenant_id = :t AND action = 'refresh_retried'"
            ),
            {"t": world.a},
        ).scalar_one()
    assert audited == 1


def test_a_failed_calculation_says_why(world: World, it: TestClient, settings: Settings) -> None:
    import_id = uuid.UUID(_import(it))
    with tenant_conn(settings, world.a) as conn:
        conn.execute(text("DELETE FROM operation_events WHERE plant_code = 'PLANT-1'"))
        facts_module.start_facts(conn, world.a, "PLANT-1", import_id, "fix")
    with pytest.raises(Exception):  # noqa: B017  (the job re-raises after recording)
        facts_module.compute_facts(settings, world.a, import_id)
    status = _status(it)
    assert (status["status"], status["problem"], status["reason"]) == (
        "failed",
        "no_events",
        "fix",
    )
    assert status["numbers_at"] and status["last_event_at"] is None
