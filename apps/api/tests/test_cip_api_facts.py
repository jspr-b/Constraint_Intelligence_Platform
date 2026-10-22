"""Measured facts: calculated after each import, replaced by the next one, failures recorded."""

import shutil
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from cip_api import facts as facts_module
from cip_api.imports import import_dir
from cip_api.settings import Settings
from cip_api_testkit import World, make_client

pytestmark = pytest.mark.db
EXPORT = Path(__file__).resolve().parents[3] / "data" / "synthetic" / "plant_a" / "erp_export"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(env="dev", data_dir=tmp_path, run_jobs_inline=True)


@pytest.fixture
def it(world: World, settings: Settings) -> TestClient:
    client = make_client(settings)
    body = {"tenant_id": str(world.a), "email": world.email("it")}
    assert client.post("/auth/dev-login", json=body).status_code == 204
    return client


def _files(folder: Path) -> list[tuple[str, tuple[str, bytes, str]]]:
    return [("files", (f.name, f.read_bytes(), "text/csv")) for f in sorted(folder.iterdir())]


def _import(it: TestClient) -> dict:  # type: ignore[type-arg]
    body = it.post("/plants/PLANT-1/imports", files=_files(EXPORT / "clean" / "csv")).json()
    assert it.post(f"/imports/{body['import_id']}/run").status_code == 202
    done: dict = it.get(f"/imports/{body['import_id']}").json()  # type: ignore[type-arg]
    assert done["status"] == "done", done["error"]
    return done


def _stored(world: World) -> list[tuple[str, int]]:
    with world.owner.connect() as conn:
        return [
            (str(r[0]), r[1])
            for r in conn.execute(
                text(
                    "SELECT import_id, count(*) FROM facts WHERE tenant_id = :t "
                    "AND plant_code = 'PLANT-1' GROUP BY import_id"
                ),
                {"t": world.a},
            )
        ]


def test_an_import_calculates_the_facts(world: World, it: TestClient) -> None:
    done = _import(it)
    assert done["facts"]["status"] == "ready", done["facts"]
    assert done["facts"]["period_start_at"] and done["facts"]["period_end_at"]
    stored = _stored(world)
    assert len(stored) == 1 and stored[0][0] == done["import_id"] and stored[0][1] > 1000
    with world.owner.connect() as conn:
        row = conn.execute(
            text(
                "SELECT value, formula_id, formula_version, confidence, inputs FROM facts "
                "WHERE tenant_id = :t AND subject_code = 'PNT-01' AND measure = 'utilisation_pct' "
                "AND period_kind = 'all'"
            ),
            {"t": world.a},
        ).one()
    assert row.value == pytest.approx(99.88, abs=0.05)
    assert (row.formula_id, row.formula_version, row.confidence) == (
        "utilisation_pct_v1",
        1,
        "high",
    )
    assert '"running_min"' in row.inputs


def test_a_new_import_replaces_the_plants_facts(world: World, it: TestClient) -> None:
    first = _import(it)
    count = _stored(world)[0][1]
    second = _import(it)
    assert _stored(world) == [(second["import_id"], count)]
    assert it.get(f"/imports/{first['import_id']}").json()["facts"]["status"] == "ready"


def test_a_failed_calculation_is_recorded(world: World, it: TestClient, settings: Settings) -> None:
    done = _import(it)
    import_id = uuid.UUID(done["import_id"])
    shutil.rmtree(import_dir(settings, world.a, "PLANT-1", import_id) / "standard")
    from cip_api.auth.sessions import tenant_conn

    with tenant_conn(settings, world.a) as conn:
        facts_module.start_facts(conn, world.a, "PLANT-1", import_id)
    with pytest.raises(Exception):  # noqa: B017  (the job re-raises after recording)
        facts_module.compute_facts(settings, world.a, import_id)
    failed = it.get(f"/imports/{import_id}").json()["facts"]
    assert failed["status"] == "failed" and failed["error"].startswith("facts:")
    assert _stored(world)[0][1] > 1000, "the old facts stay until a calculation succeeds"


def test_outside_tests_the_calculation_is_queued(
    world: World, it: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dramatiq.brokers.stub import StubBroker

    from cip_api import imports, jobs

    body = it.post("/plants/PLANT-1/imports", files=_files(EXPORT / "clean" / "csv")).json()
    stub = StubBroker()
    monkeypatch.setattr(jobs, "broker", lambda: stub)
    queued = Settings(env="dev", data_dir=tmp_path, run_jobs_inline=False)
    imports.run_import(queued, world.a, uuid.UUID(body["import_id"]))
    message = stub.queues["default"].get_nowait()
    assert b'"actor_name":"compute_facts"' in message.replace(b" ", b"")
    assert it.get(f"/imports/{body['import_id']}").json()["facts"]["status"] == "calculating"


def test_facts_are_read_as_figures_filtered_by_period(world: World, it: TestClient) -> None:
    done = _import(it)
    body = it.get(
        "/plants/PLANT-1/facts",
        params={"family": ["utilisation", "oee"], "resource_code": "PNT-01"},
    ).json()
    assert body["run"]["status"] == "ready" and body["import_id"] == done["import_id"]
    by_measure = {f["measure"]: f for f in body["facts"]}
    assert set(by_measure) == {
        "utilisation_pct",
        "availability_ratio",
        "performance_ratio",
        "quality_ratio",
        "oee_ratio",
    }
    busy = by_measure["utilisation_pct"]["figure"]
    assert busy["value"] == pytest.approx(99.88, abs=0.05) and busy["unit"] == "pct"
    assert busy["formula_id"] == "utilisation_pct_v1" and busy["period_start_at"]
    assert busy["inputs"]["running_min"]["formula_id"] == "machine_state_min_v1"

    periods = it.get("/plants/PLANT-1/facts/periods").json()
    weeks = [p for p in periods if p["period_kind"] == "week"]
    assert len(weeks) >= 10 and any(p["period_kind"] == "all" for p in periods)
    one = it.get(
        "/plants/PLANT-1/facts",
        params={
            "family": "utilisation",
            "period_kind": "week",
            "period_start_at": weeks[2]["period_start_at"],
        },
    ).json()["facts"]
    assert len(one) == 6 and {f["period_kind"] for f in one} == {"week"}
    every_week = it.get(
        "/plants/PLANT-1/facts", params={"family": "utilisation", "period_kind": "week"}
    ).json()["facts"]
    assert len(every_week) == 6 * len(weeks)


def test_task_times_name_their_operation_and_unknown_machines_are_empty(
    world: World, it: TestClient
) -> None:
    _import(it)
    facts = it.get("/plants/PLANT-1/facts", params={"family": "task_time"}).json()["facts"]
    assert facts and all(f["operation"] for f in facts)
    empty = it.get("/plants/PLANT-1/facts", params={"resource_code": "NOPE"}).json()
    assert empty["facts"] == [] and empty["run"]["status"] == "ready"


def test_before_any_import_there_are_no_facts(it: TestClient) -> None:
    body = it.get("/plants/PLANT-1/facts").json()
    assert body == {"plant_code": "PLANT-1", "run": None, "import_id": None, "facts": []}
    assert it.get("/plants/NO-SUCH/facts").json()["code"] == "plant_not_found"


def test_downtime_by_reason_and_the_day_timeline(world: World, it: TestClient) -> None:
    _import(it)
    reasons = it.get(
        "/plants/PLANT-1/facts", params={"family": "down_reason", "resource_code": "PNT-01"}
    ).json()["facts"]
    assert {f["reason_code"] for f in reasons} >= {"MECH"}
    assert all(f["figure"]["formula_id"] == "down_reason_min_v1" for f in reasons)
    days = it.get(
        "/plants/PLANT-1/facts",
        params={"family": "state", "resource_code": "PNT-01", "period_kind": "day"},
    ).json()["facts"]
    assert len({f["figure"]["period_start_at"] for f in days}) >= 60
