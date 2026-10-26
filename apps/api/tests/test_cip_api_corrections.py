"""Rows fixed in the app (ADR-0010 point 7): next to the original, checked, undone, listed."""

import csv
import io
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from cip_api.settings import Settings
from cip_api_testkit import World, make_client

pytestmark = pytest.mark.db
DATA = Path(__file__).resolve().parents[3] / "data" / "synthetic"
BROKEN = DATA / "import_cases" / "broken" / "upload_1"
EVENTS = "mes_events.csv"
WHY = "time typed wrong at the bench terminal"


def _client(world: World, tmp_path: Path, role: str) -> TestClient:
    client = make_client(Settings(env="dev", data_dir=tmp_path, run_jobs_inline=True))
    body = {"tenant_id": str(world.a), "email": world.email(role)}
    assert client.post("/auth/dev-login", json=body).status_code == 204
    return client


@pytest.fixture
def it(world: World, tmp_path: Path) -> TestClient:
    return _client(world, tmp_path, "it")


@pytest.fixture
def broken(it: TestClient) -> dict[str, Any]:
    files = [("files", (p.name, p.read_bytes(), "text/csv")) for p in sorted(BROKEN.iterdir())]
    body = it.post("/plants/PLANT-1/imports", files=files).json()
    assert it.post(f"/imports/{body['import_id']}/run").status_code == 202
    done: dict[str, Any] = it.get(f"/imports/{body['import_id']}").json()
    return done


def _events(world: World) -> int:
    with world.owner.connect() as conn:
        return int(
            conn.execute(
                text("SELECT count(*) FROM operation_events WHERE tenant_id = :t"), {"t": world.a}
            ).scalar_one()
        )


def _fix(it: TestClient, import_id: str, **body: Any) -> Any:
    return it.post(f"/imports/{import_id}/corrections", json={"file": EVENTS, **body})


def test_the_rejected_rows_list_says_rule_column_and_value(
    it: TestClient, broken: dict[str, Any]
) -> None:
    rows = it.get(f"/imports/{broken['import_id']}/rejected-rows").json()
    assert (rows["total"], rows["codes"], rows["fixed"]) == (5, {"not_a_datetime": 5}, 0)
    first = rows["rows"][0]
    assert (first["line"], first["column"], first["value"], first["code"]) == (
        101,
        "Tijdstip",
        "not a time",
        "not_a_datetime",
    )
    assert rows["datetime_format"] == "20-07-2026 10:11"
    paged = it.get(f"/imports/{broken['import_id']}/rejected-rows?offset=4&limit=2").json()
    assert [r["line"] for r in paged["rows"]] == [6001] and paged["shown"] == 5
    none = it.get(f"/imports/{broken['import_id']}/rejected-rows?code=empty").json()
    assert none["shown"] == 0 and none["rows"] == []


def test_a_fix_is_checked_by_the_import_rules_before_it_is_saved(
    world: World, it: TestClient, broken: dict[str, Any]
) -> None:
    i = broken["import_id"]
    no_reason = _fix(it, i, line=101, column="Tijdstip", value="20-07-2026 10:11", reason=" ")
    assert no_reason.status_code == 422 and "Say why" in no_reason.json()["message"]
    wrong = _fix(it, i, line=101, column="Tijdstip", value="32-07-2026 10:11", reason=WHY)
    assert wrong.status_code == 422
    assert "written like 20-07-2026 10:11" in wrong.json()["message"]
    personal = _fix(it, i, line=101, column="Medewerker", value="x", reason=WHY)
    assert personal.status_code == 422 and "personal" in personal.json()["message"]
    assert _fix(it, i, line=99999, column="Tijdstip", value="x", reason=WHY).status_code == 404
    assert _fix(it, i, line=101, column="Nope", value="x", reason=WHY).status_code == 422
    other = it.post(f"/imports/{i}/corrections", json={"file": "x.csv", "line": 2, "reason": WHY})
    assert other.status_code == 404
    assert _events(world) == 7079  # nothing was saved


def test_a_fix_rebuilds_the_plant_and_undo_brings_the_original_back(
    world: World, it: TestClient, broken: dict[str, Any], tmp_path: Path
) -> None:
    i = broken["import_id"]
    source = tmp_path.glob(f"**/{i}/source/{EVENTS}")
    before = next(source).read_bytes()
    made = _fix(it, i, line=101, column="Tijdstip", value="20-07-2026 10:11", reason=WHY)
    assert made.status_code == 201, made.text
    fix = made.json()
    assert (fix["original"], fix["value"], fix["role"], fix["action"]) == (
        "not a time",
        "20-07-2026 10:11",
        "it",
        "set",
    )
    assert fix["event_at"].startswith("2026-07-20T08:11")
    assert _events(world) == 7080
    assert next(tmp_path.glob(f"**/{i}/source/{EVENTS}")).read_bytes() == before
    events = next(
        f
        for f in it.get("/plants/PLANT-1/data-quality").json()["files"]
        if f["file"] == "events.csv"
    )
    assert (events["rejected"], events["fixed"]) == (4, 1)
    assert events["reasons"] == {"not_a_datetime": 4}  # the rule's code, said in plain words
    rows = it.get(f"/imports/{i}/rejected-rows").json()
    assert (
        rows["fixed"] == 1
        and rows["rows"][0]["correction"]["correction_id"] == fix["correction_id"]
    )
    again = _fix(it, i, line=101, exclude=True, reason="not a real touchpoint")
    assert again.status_code == 201 and _events(world) == 7079
    listed = it.get("/plants/PLANT-1/corrections").json()
    assert [(c["action"], c["undone"]) for c in listed] == [("exclude", False), ("set", True)]
    undone = it.delete(f"/corrections/{again.json()['correction_id']}")
    assert undone.status_code == 200 and undone.json()["undone"] is True
    assert _events(world) == 7079  # the original line is rejected again
    assert it.delete(f"/corrections/{again.json()['correction_id']}").status_code == 409
    assert it.get(f"/imports/{i}").json()["facts"]["status"] == "ready"


def test_corrections_download_as_csv_and_other_roles_only_read(
    world: World, it: TestClient, broken: dict[str, Any], tmp_path: Path
) -> None:
    i = broken["import_id"]
    _fix(it, i, line=1501, column="Tijdstip", value="04-08-2026 17:36", reason=WHY)
    got = it.get("/plants/PLANT-1/corrections.csv")
    assert got.status_code == 200 and got.headers["content-type"].startswith("text/csv")
    (row,) = list(csv.DictReader(io.StringIO(got.text)))
    assert (row["file"], row["line"], row["value_uploaded"], row["value_fixed"]) == (
        EVENTS,
        "1501",
        "not a time",
        "04-08-2026 17:36",
    )
    director = _client(world, tmp_path, "plant_director")
    assert len(director.get("/plants/PLANT-1/corrections").json()) == 1
    refused = director.post(
        f"/imports/{i}/corrections",
        json={"file": EVENTS, "line": 101, "exclude": True, "reason": WHY},
    )
    assert refused.status_code == 403
    audit = world.owner.connect().execute(
        text("SELECT count(*) FROM audit_log WHERE tenant_id = :t AND action = 'row_fixed'"),
        {"t": world.a},
    )
    assert audit.scalar_one() == 1


CLEAN = DATA / "plant_a" / "erp_export" / "clean" / "csv"


def _windows(world: World) -> int:
    with world.owner.connect() as conn:
        return int(
            conn.execute(
                text("SELECT count(*) FROM calendar_windows WHERE tenant_id = :t"),
                {"t": world.a},
            ).scalar_one()
        )


def test_an_imported_calendar_row_removed_stays_out_until_undone(
    world: World, it: TestClient
) -> None:
    files = [("files", (p.name, p.read_bytes(), "text/csv")) for p in sorted(CLEAN.iterdir())]
    first = it.post("/plants/PLANT-1/imports", files=files).json()["import_id"]
    assert it.post(f"/imports/{first}/run").status_code == 202
    with world.owner.connect() as conn:
        window = conn.execute(
            text(
                "SELECT id FROM calendar_windows WHERE tenant_id = :t AND import_id IS NOT NULL "
                "ORDER BY start_at LIMIT 1"
            ),
            {"t": world.a},
        ).scalar_one()
    count = _windows(world)
    url = f"/plants/PLANT-1/calendar/windows/{window}"
    no_reason = it.delete(url)
    assert no_reason.status_code == 422 and "came from an upload" in no_reason.json()["message"]
    assert it.delete(f"{url}?reason=shift%20was%20cancelled").status_code == 204
    assert _windows(world) == count - 1
    assert it.post(f"/imports/{first}/run").status_code == 202  # a rebuild: it stays out
    assert _windows(world) == count - 1
    (removal,) = it.get("/plants/PLANT-1/corrections").json()
    assert (removal["action"], removal["target"], removal["reason"]) == (
        "remove",
        "calendar_windows",
        "shift was cancelled",
    )
    assert it.delete(f"/corrections/{removal['correction_id']}").status_code == 200
    assert _windows(world) == count  # back from the upload


def test_a_step_with_touchpoints_or_a_station_in_use_is_not_removed(
    world: World, it: TestClient
) -> None:
    files = [("files", (p.name, p.read_bytes(), "text/csv")) for p in sorted(CLEAN.iterdir())]
    body = it.post("/plants/PLANT-1/imports", files=files).json()
    assert it.post(f"/imports/{body['import_id']}/run").status_code == 202
    step = it.delete("/plants/PLANT-1/resources/WLD-01?reason=closed")
    assert step.status_code == 409 and "touchpoints" in step.json()["message"]
    setup = it.get("/plants/PLANT-1/setup").json()
    station = next(s for s in setup["stations"] if s["machines"])
    assert station["imported"] and station["machines"][0]["imported"]
    used = it.delete(f"/plants/PLANT-1/stations/{station['station_code']}?reason=x")
    assert used.status_code == 409
    assert it.delete("/plants/PLANT-1/stations/NOPE?reason=x").status_code == 404


def test_numbers_that_use_fixed_rows_say_so(
    world: World, it: TestClient, broken: dict[str, Any]
) -> None:
    case = [
        (101, "20-07-2026 10:11"),
        (1501, "04-08-2026 17:36"),
        (3001, "24-08-2026 06:37"),
    ]
    for line, value in case:
        made = _fix(it, broken["import_id"], line=line, column="Tijdstip", value=value, reason=WHY)
        assert made.status_code == 201, made.text
    with world.owner.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT period_kind, period_start_at, inputs FROM facts WHERE tenant_id = :t "
                "AND family = 'loss' AND subject_code = 'PNT-01'"
            ),
            {"t": world.a},
        ).all()
    whole = [json.loads(r.inputs) for r in rows if r.period_kind == "all"]
    assert whole and all(i.get("fixed_rows") == 3 for i in whole)
    september = [
        json.loads(r.inputs)
        for r in rows
        if r.period_kind == "month" and r.period_start_at.month == 9
    ]
    assert september and all("fixed_rows" not in i for i in september)  # fixes are Jul and Aug
