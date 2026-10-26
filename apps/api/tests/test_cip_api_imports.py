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
        "events": "ok",
        "steps": "ok",
        "shifts": "ok",
    }
    optional = {m["key"]: m["status"] for m in done["optional_set"]}
    assert optional["orders"] == optional["products"] == optional["routings"] == "ok"
    assert optional["holidays"] == "check"  # plant_a lists no holidays: a person confirms
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
    # A folder in the name is dropped: the file lands inside the import as escape.csv.
    escaped = it.post(
        "/plants/PLANT-1/imports", files=[("files", ("../escape.csv", b"a;b\n", "text/csv"))]
    )
    assert escaped.status_code == 201 and escaped.json()["file_names"] == ["escape.csv"]
    exe = [("files", ("tool.exe", b"x", "application/octet-stream"))]
    refused = it.post("/plants/PLANT-1/imports", files=exe)
    assert (refused.status_code, refused.json()["code"]) == (422, "no_table_files")
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
    assert done["failed_step"] == "read"
    assert done["error"].startswith("read:")


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
    other = client.post("/plants/PLANT-1/imports", files=_files(EXPORT / "clean" / "csv")).json()
    assert client.post(f"/imports/{other['import_id']}/run").status_code == 409


def test_file_check_before_running(client_as: Callable[[str], TestClient]) -> None:
    it = client_as("it")
    files = _files(EXPORT / "clean" / "csv")
    windows = (
        "Artikel;Omschrijving;Productgroep;Kleurgroep;Verkoopprijs;Variabele kosten\n"
        "F-200;Café frame;Frames;RAL7016;980,00;430,00\n"
    )
    files = [f for f in files if f[1][0] != "artikelen.csv"]
    files += [
        ("files", ("artikelen.csv", windows.encode("cp1252"), "text/csv")),
        ("files", ("notes.csv", b"just some text\n", "text/csv")),
        ("files", ("rooster.xlsx", b"broken", "application/octet-stream")),
    ]
    files = [f for f in files if f[1][0] != "rooster.csv"]
    body = it.post("/plants/PLANT-1/imports", files=files).json()
    by_name = {f["name"]: f for f in body["files"]}
    events = by_name["mes_events.csv"]
    assert events["recognised_as"] == "mes_events" and events["feeds"] == ["events"]
    assert events["readable"] and events["rows"] > 1000 and events["delimiter"] == ";"
    assert events["personal_columns"] == ["Medewerker"]
    assert all("Medewerker" not in row for row in events["preview"]) and len(events["preview"]) == 5
    products = by_name["artikelen.csv"]
    assert (
        products["encoding"] == "cp1252" and products["preview"][0]["Omschrijving"] == "Café frame"
    )
    notes = by_name["notes.csv"]
    assert notes["recognised_as"] is None and notes["problem"] == "single_column"
    assert by_name["rooster.xlsx"]["problem"] == "unreadable_excel"
    needed = {n["key"]: (n["present"], n["minimum"]) for n in body["needed"]}
    assert needed == {
        "events": (True, True),
        "steps": (True, True),
        "shifts": (False, True),  # rooster.xlsx is unreadable
        "orders": (True, False),
        "products": (True, False),
        "routings": (True, False),
    }
    assert "mes_events" in body["expected_files"]


def test_the_event_log_steps_and_shifts_are_enough_to_start(
    client_as: Callable[[str], TestClient],
) -> None:
    """ADR-0009: the event log, a steps list and a shift sheet are enough to start; jobs,
    products and routings add euros and confidence, and getting started says so."""
    it = client_as("it")
    keep = {"werkplekken.csv", "mes_events.csv", "rooster.csv"}
    files = [f for f in _files(EXPORT / "clean" / "csv") if f[1][0] in keep]
    body = it.post("/plants/PLANT-1/imports", files=files).json()
    assert it.post(f"/imports/{body['import_id']}/run").status_code == 202
    done = it.get(f"/imports/{body['import_id']}").json()
    assert done["status"] == "done", done["error"]
    stored = done["report"]["stored_rows"]
    assert stored["resources"] == 6 and stored["events"] > 1000
    assert not {"products", "routings", "orders"} & set(stored)
    assert done["report"]["quality"]["files_missing"] == []
    assert {m["status"] for m in done["minimum_set"]} == {"ok"}
    optional = {m["key"]: m["status"] for m in done["optional_set"]}
    assert optional["orders"] == optional["products"] == optional["routings"] == "missing"
    onboarding = it.get("/onboarding").json()
    check = next(s for s in onboarding["steps"] if s["key"] == "check")
    assert check["state"] == "done" and check["detail"] == "optional"
    assert {"orders", "products", "routings"} <= set(check["missing"])


def test_a_workshop_scan_export_is_recognised_and_imported(
    world: World, client_as: Callable[[str], TestClient]
) -> None:
    """Plant D (ADR-0009): its own format is recognised by its file names; the operator column
    is dropped; steps, the shared team and the scans are stored."""
    plant_d = EXPORT.parents[1] / "plant_d" / "erp_export" / "clean" / "csv"
    it = client_as("it")
    body = it.post("/plants/PLANT-1/imports", files=_files(plant_d)).json()
    assert body["status"] == "uploaded" and len(body["files"]) == 6
    assert all(f["recognised_as"] for f in body["files"])
    scans = next(s for s in body["sources"] if s["source"] == "scans")
    assert {c["name"]: c["status"] for c in scans["columns"]}["Operator"] == "not_imported"
    needed = {n["key"]: n["minimum"] for n in body["needed"] if n["present"]}
    assert needed == {
        "events": True,
        "steps": True,
        "shifts": True,
        "orders": False,
        "teams": False,
    }
    assert all(n["sources"] for n in body["needed"])

    assert it.post(f"/imports/{body['import_id']}/run").status_code == 202
    done = it.get(f"/imports/{body['import_id']}").json()
    assert done["status"] == "done", done["error"]
    assert done["report"]["import"]["dropped_columns"]["scans"] == ["Operator"]
    stored = done["report"]["stored_rows"]
    assert stored["resources"] == 6 and stored["teams"] == 1 and stored["events"] == 28541
    with world.owner.connect() as conn:
        team = conn.execute(
            text("SELECT team_code FROM teams WHERE tenant_id = :t AND plant_code = 'PLANT-1'"),
            {"t": world.a},
        ).scalar_one()
    assert team == "FINISH-TEAM"
    teams = it.get("/plants/PLANT-1/teams").json()
    assert teams == [
        {
            "team_code": "FINISH-TEAM",
            "name": "Finishing team",
            "resource_codes": ["FINISH", "PACK"],
            "size_max": 3,
        }
    ]
