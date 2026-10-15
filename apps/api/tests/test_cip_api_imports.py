"""Import page backend: upload plant_a's ERP-style export, preview, run, stored data."""

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


def _files(folder: Path) -> list[tuple[str, tuple[str, bytes, str]]]:
    return [("files", (f.name, f.read_bytes(), "text/csv")) for f in sorted(folder.iterdir())]


def test_upload_preview_and_run(world: World, client_as: Callable[[str], TestClient]) -> None:
    it = client_as("it")
    created = it.post("/plants/PLANT-1/imports", files=_files(EXPORT / "clean" / "csv"))
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "uploaded" and len(body["files"]) == 10
    events = next(s for s in body["sources"] if s["source"] == "mes_events")
    status = {c["name"]: c["status"] for c in events["columns"]}
    assert status["Medewerker"] == "not_imported"
    assert "mapped" in status.values() and events["missing_columns"] == []
    medewerker = next(c for c in events["columns"] if c["name"] == "Medewerker")
    assert medewerker["example"] is None and medewerker["fields"] == []
    machine = next(c for c in events["columns"] if "events.resource_code" in c["fields"])
    assert machine["example"] and "code_table:resource" in machine["conversions"]

    assert it.post(f"/imports/{body['import_id']}/run").status_code == 202
    done = it.get(f"/imports/{body['import_id']}").json()
    assert done["status"] == "done", done["error"]
    assert {m["key"]: m["status"] for m in done["minimum_set"]} == {
        "orders": "ok",
        "routings": "ok",
        "products": "ok",
        "events": "ok",
        "calendar": "check",  # plant_a lists no holidays: a person confirms there are none
    }
    assert done["report"]["import"]["dropped_columns"]["mes_events"] == ["Medewerker"]
    assert done["report"]["stored_rows"]["resources"] == 6
    with world.owner.connect() as conn:
        machines = conn.execute(
            text("SELECT count(*) FROM resources WHERE tenant_id = :t AND plant_code = 'PLANT-1'"),
            {"t": world.a},
        ).scalar_one()
        columns = (
            conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'operation_events'"
                )
            )
            .scalars()
            .all()
        )
    assert machines == 6 and "medewerker" not in [c.lower() for c in columns]
    listed = it.get("/plants/PLANT-1/imports").json()
    assert [i["import_id"] for i in listed] == [body["import_id"]]


def test_defects_still_import_with_gaps(client_as: Callable[[str], TestClient]) -> None:
    it = client_as("it")
    body = it.post("/plants/PLANT-1/imports", files=_files(EXPORT / "defects" / "csv")).json()
    it.post(f"/imports/{body['import_id']}/run")
    done = it.get(f"/imports/{body['import_id']}").json()
    assert done["status"] == "done"
    assert done["report"]["import"]["row_errors"], "defect rows are reported, not guessed"


def test_only_import_roles_upload(client_as: Callable[[str], TestClient]) -> None:
    files = _files(EXPORT / "clean" / "csv")[:1]
    assert client_as("shift_lead").post("/plants/PLANT-1/imports", files=files).status_code == 403
    assert client_as("planner").post("/plants/PLANT-1/imports", files=files).status_code == 201


def test_bad_uploads_are_refused(client_as: Callable[[str], TestClient]) -> None:
    it = client_as("it")
    bad = [("files", ("../escape.csv", b"x", "text/csv"))]
    assert it.post("/plants/PLANT-1/imports", files=bad).status_code == 422
    exe = [("files", ("tool.exe", b"x", "application/octet-stream"))]
    assert it.post("/plants/PLANT-1/imports", files=exe).status_code == 422
    ok = [("files", ("orders.csv", b"a;b\n", "text/csv"))]
    assert it.post("/plants/NO-SUCH/imports", files=ok).status_code == 404


def test_a_broken_file_fails_the_import_with_a_reason(
    client_as: Callable[[str], TestClient],
) -> None:
    it = client_as("it")
    broken = [("files", ("werkplekken.xlsx", b"not an excel file", "application/octet-stream"))]
    body = it.post("/plants/PLANT-1/imports", files=broken).json()
    assert body["sources"][0]["readable"] is False
    it.post(f"/imports/{body['import_id']}/run")
    done = it.get(f"/imports/{body['import_id']}").json()
    assert done["status"] == "failed" and done["error"]


def test_outside_tests_the_run_is_queued_for_a_worker(
    world: World, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dramatiq.brokers.stub import StubBroker

    from cip_api import jobs

    stub = StubBroker()
    monkeypatch.setattr(jobs, "broker", lambda: stub)
    client = make_client(Settings(env="dev", data_dir=tmp_path))
    login = {"tenant_id": str(world.a), "email": world.email("it")}
    assert client.post("/auth/dev-login", json=login).status_code == 204
    body = client.post("/plants/PLANT-1/imports", files=_files(EXPORT / "clean" / "csv")).json()
    queued = client.post(f"/imports/{body['import_id']}/run").json()
    assert queued["status"] == "running"
    message = stub.queues["default"].get_nowait()
    assert b'"actor_name":"run_import"' in message.replace(b" ", b"")
    assert client.post(f"/imports/{body['import_id']}/run").status_code == 409
