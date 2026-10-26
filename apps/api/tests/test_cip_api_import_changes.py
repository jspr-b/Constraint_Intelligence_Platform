"""Import history, changing an upload's files, versions and the preview (ADR-0010)."""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from cip_api.settings import Settings
from cip_api_testkit import World, make_client

pytestmark = pytest.mark.db
DATA = Path(__file__).resolve().parents[3] / "data" / "synthetic"
CASES = DATA / "import_cases"
CLEAN = DATA / "plant_a" / "erp_export" / "clean" / "csv"
EVENTS = "mes_events.csv"


@pytest.fixture
def it(world: World, tmp_path: Path) -> TestClient:
    client = make_client(Settings(env="dev", data_dir=tmp_path, run_jobs_inline=True))
    body = {"tenant_id": str(world.a), "email": world.email("it")}
    assert client.post("/auth/dev-login", json=body).status_code == 204
    return client


def _files(*paths: Path) -> list[tuple[str, tuple[str, bytes, str]]]:
    return [("files", (p.name, p.read_bytes(), "text/csv")) for p in paths]


def _upload(it: TestClient, folder: Path) -> dict[str, Any]:
    body: dict[str, Any] = it.post(
        "/plants/PLANT-1/imports", files=_files(*sorted(folder.iterdir()))
    ).json()
    return body


def _run(it: TestClient, import_id: str) -> dict[str, Any]:
    assert it.post(f"/imports/{import_id}/run").status_code == 202
    done: dict[str, Any] = it.get(f"/imports/{import_id}").json()
    assert done["status"] == "done", done["error"]
    return done


def _count(world: World, sql: str) -> int:
    with world.owner.connect() as conn:
        return int(conn.execute(text(sql), {"t": world.a}).scalar_one())


def test_history_lists_every_import_with_role_and_the_data_in_use(
    world: World, it: TestClient
) -> None:
    first = _run(it, _upload(it, CASES / "split" / "upload_1")["import_id"])
    second = _run(it, _upload(it, CASES / "split" / "upload_2")["import_id"])
    listed = it.get("/plants/PLANT-1/imports").json()
    assert [i["import_id"] for i in listed] == [second["import_id"], first["import_id"]]
    assert {i["by_role"] for i in listed} == {"it"} and {i["status"] for i in listed} == {"done"}
    in_use = it.get("/plants/PLANT-1/data-in-use").json()
    assert [(u["import_id"], u["events"]) for u in in_use] == [
        (first["import_id"], 3545),
        (second["import_id"], 3539),
    ]
    assert "resources" in in_use[0]["lists"] and in_use[1]["lists"] == []


def test_before_the_run_files_are_added_replaced_and_removed(
    world: World, it: TestClient, tmp_path: Path
) -> None:
    body = _upload(it, CASES / "split" / "upload_2")
    import_id = body["import_id"]
    added = it.post(f"/imports/{import_id}/files", files=_files(CLEAN / "werkplekken.csv")).json()
    assert added["import_id"] == import_id and len(added["files"]) == 2
    assert {f["recognised_as"] for f in added["files"]} == {"mes_events", "werkplekken"}
    other = tmp_path / EVENTS
    other.write_bytes((CLEAN / EVENTS).read_bytes())
    replaced = it.post(f"/imports/{import_id}/files", files=_files(other)).json()
    events = next(f for f in replaced["files"] if f["name"] == EVENTS)
    assert events["rows"] == 7084  # the whole log now, not weeks 7-12
    removed = it.delete(f"/imports/{import_id}/files/werkplekken.csv")
    assert removed.status_code == 200 and [f["name"] for f in removed.json()["files"]] == [EVENTS]
    last = it.delete(f"/imports/{import_id}/files/{EVENTS}")
    assert last.status_code == 422 and "at least one file" in last.json()["message"]
    assert it.delete(f"/imports/{import_id}/files/nope.csv").status_code == 404
    bad = it.post(f"/imports/{import_id}/files", files=[("files", ("x.exe", b"MZ", "a/b"))])
    assert bad.status_code == 422
    actions = _count(
        world,
        "SELECT count(*) FROM audit_log WHERE tenant_id = :t "
        "AND action IN ('import_file_added', 'import_file_removed')",
    )
    assert actions == 3


def test_after_the_run_a_replaced_file_is_a_new_version_and_the_old_one_is_kept(
    world: World, it: TestClient
) -> None:
    broken = _run(it, _upload(it, CASES / "broken" / "upload_1")["import_id"])
    assert len(broken["report"]["import"]["row_errors"]) == 5
    version = it.post(f"/imports/{broken['import_id']}/files", files=_files(CLEAN / EVENTS)).json()
    assert version["import_id"] != broken["import_id"]
    assert version["replaces"] == broken["import_id"] and version["status"] == "uploaded"
    assert len(version["files"]) == 10
    assert it.get(f"/imports/{broken['import_id']}").json()["status"] == "done"  # until it runs
    done = _run(it, version["import_id"])
    assert done["report"]["import"]["row_errors"] == []
    old = it.get(f"/imports/{broken['import_id']}").json()
    assert old["status"] == "replaced" and old["replaced_by"] == version["import_id"]
    events = _count(
        world,
        "SELECT count(*) FROM operation_events WHERE tenant_id = :t AND plant_code = 'PLANT-1'",
    )
    assert events == 7084
    gone = _count(
        world,
        "SELECT count(*) FROM operation_events WHERE tenant_id = :t "
        f"AND import_id = '{broken['import_id']}'",
    )
    assert gone == 0
    again = it.post(f"/imports/{broken['import_id']}/files", files=_files(CLEAN / EVENTS))
    assert again.status_code == 409


def test_the_preview_says_what_an_upload_adds_and_changes_nothing(
    world: World, it: TestClient
) -> None:
    _run(it, _upload(it, CASES / "split" / "upload_1")["import_id"])
    second = _upload(it, CASES / "split" / "upload_2")
    needed = {n["key"]: (n["present"], n["in_plant"]) for n in second["needed"]}
    assert needed["events"] == (True, False)  # in this upload
    assert needed["steps"] == needed["shifts"] == (False, True)  # kept from the first upload
    preview = it.get(f"/imports/{second['import_id']}/preview")
    assert preview.status_code == 200, preview.text
    p = preview.json()
    assert (p["events_before"], p["events_added"], p["events_removed"]) == (3545, 3539, 0)
    assert p["events_after"] == 7084 and p["warnings"] == [] and p["lists"] == []
    assert p["period_after"][1] > p["period_before"][1]
    stored = _count(world, "SELECT count(*) FROM operation_events WHERE tenant_id = :t")
    assert stored == 3545  # the preview rolled back
    _run(it, second["import_id"])
    assert it.get(f"/imports/{second['import_id']}/preview").status_code == 409


def test_the_preview_warns_when_steps_with_events_would_go(
    world: World, it: TestClient, tmp_path: Path
) -> None:
    _run(it, _upload(it, CLEAN)["import_id"])
    steps = tmp_path / "werkplekken.csv"
    lines = (CLEAN / "werkplekken.csv").read_text(encoding="utf-8").splitlines()
    steps.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    fewer = it.post("/plants/PLANT-1/imports", files=_files(steps)).json()
    p = it.get(f"/imports/{fewer['import_id']}/preview").json()
    (change,) = [c for c in p["lists"] if c["name"] == "resources"]
    assert (change["before"], change["after"], len(change["gone"])) == (6, 5, 1)
    (warning,) = [w for w in p["warnings"] if w["code"] == "steps_removed_with_events"]
    assert warning["items"] == change["gone"]
