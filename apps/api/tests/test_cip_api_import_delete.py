"""Delete an upload, an import or all data of a plant (ADR-0010 point 9): gone for real, one
history line kept, the plant rebuilt from the rest, and the confirmation shows what changes."""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from cip_api.db.plant_store import TABLES
from cip_api.settings import Settings
from cip_api_testkit import World, make_client

pytestmark = pytest.mark.db
CASES = Path(__file__).resolve().parents[3] / "data" / "synthetic" / "import_cases"
CLEAN = CASES.parent / "plant_a" / "erp_export" / "clean" / "csv"
PER_IMPORT = (*TABLES.values(), "corrections", "facts", "detections", "fact_runs")


def _client(world: World, tmp_path: Path, role: str) -> TestClient:
    client = make_client(Settings(env="dev", data_dir=tmp_path, run_jobs_inline=True))
    body = {"tenant_id": str(world.a), "email": world.email(role)}
    assert client.post("/auth/dev-login", json=body).status_code == 204
    return client


@pytest.fixture
def it(world: World, tmp_path: Path) -> TestClient:
    return _client(world, tmp_path, "it")


def _upload(it: TestClient, folder: Path, run: bool = True) -> dict[str, Any]:
    files = [("files", (p.name, p.read_bytes(), "text/csv")) for p in sorted(folder.iterdir())]
    body: dict[str, Any] = it.post("/plants/PLANT-1/imports", files=files).json()
    if run:
        assert it.post(f"/imports/{body['import_id']}/run").status_code == 202
        body = it.get(f"/imports/{body['import_id']}").json()
    return body


def _count(world: World, sql: str, **params: Any) -> int:
    with world.owner.connect() as conn:
        return int(conn.execute(text(sql), {"t": world.a, **params}).scalar_one())


def _events(world: World) -> int:
    return _count(world, "SELECT count(*) FROM operation_events WHERE tenant_id = :t")


def _left_of(world: World, import_id: str) -> dict[str, int]:
    """Rows anywhere that still belong to the import; empty when it is gone."""
    found = {
        t: _count(world, f"SELECT count(*) FROM {t} WHERE import_id = :i", i=import_id)
        for t in PER_IMPORT
    }
    return {t: n for t, n in found.items() if n}


def _folder(tmp_path: Path, world: World, import_id: str) -> Path:
    return tmp_path / str(world.a) / "PLANT-1" / "imports" / import_id


def test_an_upload_that_never_ran_is_deleted_and_one_history_line_stays(
    world: World, it: TestClient, tmp_path: Path
) -> None:
    upload = _upload(it, CASES / "split" / "upload_1", run=False)
    i = upload["import_id"]
    assert _folder(tmp_path, world, i).is_dir()
    preview = it.get(f"/imports/{i}/delete-preview").json()
    assert preview["in_use"] is False and preview["events_removed"] == 0
    assert it.delete(f"/imports/{i}").status_code == 204
    assert not _folder(tmp_path, world, i).exists()
    line = it.get(f"/imports/{i}").json()
    assert (line["status"], line["deleted_by_role"]) == ("deleted", "it")
    assert line["deleted_at"] and line["report"] is None
    assert "mes_events.csv" in line["file_names"] and line["files"] == []  # no example values
    again = it.delete(f"/imports/{i}")
    assert again.status_code == 409 and again.json()["code"] == "import_already_deleted"
    assert it.get(f"/imports/{i}/delete-preview").status_code == 409
    assert (
        _count(
            world,
            "SELECT count(*) FROM audit_log WHERE tenant_id = :t AND action = 'import_deleted' "
            "AND target = :g",
            g=f"import:{i}",
        )
        == 1
    )


def test_a_running_import_is_not_deleted(world: World, it: TestClient) -> None:
    upload = _upload(it, CASES / "split" / "upload_1", run=False)
    with world.owner.begin() as conn:
        conn.execute(
            text("UPDATE imports SET status = 'running' WHERE import_id = :i"),
            {"i": upload["import_id"]},
        )
    refused = it.delete(f"/imports/{upload['import_id']}")
    assert refused.status_code == 409 and refused.json()["code"] == "import_running"
    assert "Wait" in refused.json()["message"]


def test_the_confirmation_shows_what_goes_and_changes_nothing(world: World, it: TestClient) -> None:
    first = _upload(it, CASES / "split" / "upload_1")
    second = _upload(it, CASES / "split" / "upload_2")
    events = _events(world)
    p = it.get(f"/imports/{second['import_id']}/delete-preview").json()
    assert p["in_use"] is True and p["imports_left"] == 1 and p["falls_back_to"] is None
    assert p["events_before"] == events and p["events_after"] == 3545
    assert p["events_removed"] == events - 3545
    assert p["period_after"][1] < p["period_before"][1]
    assert {s["from_import_id"] for s in p["lists_after"]} == {first["import_id"]}
    assert _events(world) == events  # the preview is rolled back
    assert it.get(f"/imports/{second['import_id']}").json()["status"] == "done"


def test_deleting_an_import_in_use_removes_it_everywhere_and_rebuilds(
    world: World, it: TestClient, tmp_path: Path
) -> None:
    first = _upload(it, CASES / "split" / "upload_1")
    second = _upload(it, CASES / "broken" / "upload_1")
    i = second["import_id"]
    fixed = it.post(
        f"/imports/{i}/corrections",
        json={
            "file": "mes_events.csv",
            "line": 101,
            "column": "Tijdstip",
            "value": "20-07-2026 10:11",
            "reason": "typed wrong",
        },
    )
    assert fixed.status_code == 201
    assert it.get(f"/imports/{i}/delete-preview").json()["corrections"] == 1
    assert _left_of(world, i)  # rows, the correction and its numbers
    assert it.delete(f"/imports/{i}").status_code == 204
    assert _left_of(world, i) == {}
    assert not _folder(tmp_path, world, i).exists()
    assert _events(world) == 3545  # only the first upload's events
    assert it.get(f"/imports/{first['import_id']}").json()["facts"]["status"] == "ready"
    assert it.get("/plants/PLANT-1/corrections").json() == []


def test_deleting_a_new_version_brings_the_version_before_back(
    world: World, it: TestClient
) -> None:
    first = _upload(it, CASES / "split" / "upload_1")
    events = (CLEAN / "mes_events.csv").read_bytes()
    changed = it.post(
        f"/imports/{first['import_id']}/files",
        files=[("files", ("mes_events.csv", events, "text/csv"))],
    ).json()
    assert it.post(f"/imports/{changed['import_id']}/run").status_code == 202
    assert it.get(f"/imports/{first['import_id']}").json()["status"] == "replaced"
    assert _events(world) == 7084
    p = it.get(f"/imports/{changed['import_id']}/delete-preview").json()
    assert p["falls_back_to"] == first["import_id"] and p["events_after"] == 3545
    assert it.delete(f"/imports/{changed['import_id']}").status_code == 204
    assert it.get(f"/imports/{first['import_id']}").json()["status"] == "done"
    assert _events(world) == 3545


def test_deleting_the_only_import_leaves_an_empty_plant(world: World, it: TestClient) -> None:
    only = _upload(it, CASES / "split" / "upload_1")
    assert it.get(f"/imports/{only['import_id']}/delete-preview").json()["imports_left"] == 0
    assert it.delete(f"/imports/{only['import_id']}").status_code == 204
    assert _events(world) == 0
    quality = it.get("/plants/PLANT-1/data-quality").json()
    assert quality["import_id"] is None and quality["score"] is None


def test_all_data_of_a_plant_is_deleted_by_it_with_the_typed_code(
    world: World, it: TestClient, tmp_path: Path
) -> None:
    first = _upload(it, CASES / "split" / "upload_1")
    waiting = _upload(it, CASES / "split" / "upload_2", run=False)
    planner = _client(world, tmp_path, "planner")
    refused = planner.delete("/plants/PLANT-1/data?confirm=PLANT-1")
    assert refused.status_code == 403 and refused.json()["code"] == "plant_delete_it_only"
    typo = it.delete("/plants/PLANT-1/data?confirm=PLANT-2")
    assert typo.status_code == 422 and "Nothing was deleted" in typo.json()["message"]
    assert _events(world) == 3545
    assert it.delete("/plants/PLANT-1/data?confirm=PLANT-1").status_code == 204
    for t in PER_IMPORT:
        n = _count(
            world, f"SELECT count(*) FROM {t} WHERE tenant_id = :t AND plant_code = 'PLANT-1'"
        )
        assert n == 0, t
    for i in (first["import_id"], waiting["import_id"]):
        assert not _folder(tmp_path, world, i).exists()
        assert it.get(f"/imports/{i}").json()["status"] == "deleted"
    assert _count(
        world, "SELECT count(*) FROM plants WHERE tenant_id = :t AND plant_code = 'PLANT-1'"
    )
    assert (
        _count(
            world,
            "SELECT count(*) FROM audit_log WHERE tenant_id = :t AND action = 'plant_data_deleted'",
        )
        == 1
    )


def test_a_failed_upload_is_deleted(world: World, it: TestClient) -> None:
    upload = _upload(it, CASES / "split" / "upload_1", run=False)
    with world.owner.begin() as conn:
        conn.execute(
            text(
                "UPDATE imports SET status = 'failed', error = 'read:ValueError' "
                "WHERE import_id = :i"
            ),
            {"i": upload["import_id"]},
        )
    assert it.delete(f"/imports/{upload['import_id']}").status_code == 204
    line = it.get(f"/imports/{upload['import_id']}").json()
    assert line["status"] == "deleted" and line["error"] is None


def test_after_the_last_delete_getting_started_asks_for_an_upload(
    world: World, it: TestClient
) -> None:
    only = _upload(it, CASES / "split" / "upload_1")
    assert it.delete(f"/imports/{only['import_id']}").status_code == 204
    steps = {s["key"]: s["state"] for s in it.get("/onboarding?plant_code=PLANT-1").json()["steps"]}
    assert steps["upload"] == "todo"
