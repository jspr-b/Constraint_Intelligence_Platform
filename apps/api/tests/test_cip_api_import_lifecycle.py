"""Known answers for the import lifecycle (ADR-0010), fixed before the code.

Cases come from data/synthetic/import_cases (scripts/gen_import_cases.py), cut from plant A's
clean export. The answer is plant A's known answer, or the first upload's own answer; never a
number made by the engine for this test. Each test is a strict xfail until the sequence that
builds it removes the mark (CI0004: 02 history, 04 fixes, 05 delete).
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import text

from cip_api.settings import Settings
from cip_api_testkit import World, make_client

pytestmark = pytest.mark.db
DATA = Path(__file__).resolve().parents[3] / "data" / "synthetic"
CASES = DATA / "import_cases"
CLEAN = DATA / "plant_a" / "erp_export" / "clean" / "csv"
ANSWERS: dict[str, Any] = yaml.safe_load((CASES / "expected_answers.yaml").read_text())
PLANT_A: dict[str, Any] = yaml.safe_load((DATA / "plant_a" / "expected_answers.yaml").read_text())

history = pytest.mark.xfail(strict=True, reason="ADR-0010: imports as history, CI0004 seq 02")
fixes = pytest.mark.xfail(strict=True, reason="ADR-0010: fix rows in the app, CI0004 seq 04")
deletes = pytest.mark.xfail(strict=True, reason="ADR-0010: delete an import, CI0004 seq 05")


@pytest.fixture
def client_as(world: World, tmp_path: Path) -> Callable[[str], TestClient]:
    settings = Settings(env="dev", data_dir=tmp_path, run_jobs_inline=True)

    def _client(tenant: str) -> TestClient:
        client = make_client(settings)
        tenant_id = world.a if tenant == "a" else world.b
        body = {"tenant_id": str(tenant_id), "email": world.email("it", tenant)}
        assert client.post("/auth/dev-login", json=body).status_code == 204
        return client

    return _client


def _upload(it: TestClient, folder: Path) -> dict[str, Any]:
    files = [("files", (f.name, f.read_bytes(), "text/csv")) for f in sorted(folder.iterdir())]
    body = it.post("/plants/PLANT-1/imports", files=files).json()
    assert it.post(f"/imports/{body['import_id']}/run").status_code == 202
    done: dict[str, Any] = it.get(f"/imports/{body['import_id']}").json()
    assert done["status"] == "done", done["error"]
    return done


def _events(world: World, tenant: str = "a") -> int:
    with world.owner.connect() as conn:
        return int(
            conn.execute(
                text(
                    "SELECT count(*) FROM operation_events WHERE tenant_id = :t "
                    "AND plant_code = 'PLANT-1'"
                ),
                {"t": world.a if tenant == "a" else world.b},
            ).scalar_one()
        )


def _busy(world: World, tenant: str = "a") -> dict[str, float]:
    with world.owner.connect() as conn:
        return {
            r.subject_code: float(r.value)
            for r in conn.execute(
                text(
                    "SELECT subject_code, value FROM facts WHERE tenant_id = :t "
                    "AND plant_code = 'PLANT-1' AND measure = 'utilisation_pct' "
                    "AND period_kind = 'all'"
                ),
                {"t": world.a if tenant == "a" else world.b},
            )
        }


def _is_plant_a(world: World, it: TestClient) -> None:
    busy = _busy(world)
    for code, want in PLANT_A["utilisation_pct"].items():
        assert busy[code] == pytest.approx(want, abs=0.1), code
    (whole,) = it.get("/plants/PLANT-1/detection").json()["detections"]
    assert whole["resource_code"] == PLANT_A["constraint"]


@history
def test_split_uploads_give_the_answer_of_one_upload(
    world: World, client_as: Callable[[str], TestClient]
) -> None:
    case = ANSWERS["cases"]["split"]
    it = client_as("a")
    reports = [_upload(it, CASES / u)["report"] for u in case["uploads"]]
    assert [r["events"]["added"] for r in reports] == case["events_per_upload"]
    assert [r["events"]["already_there"] for r in reports] == case["events_already_there"]
    assert _events(world) == case["events_after"] == ANSWERS["events_in_plant_a"]
    _is_plant_a(world, it)


@history
def test_events_sent_again_are_counted_once(
    world: World, client_as: Callable[[str], TestClient]
) -> None:
    case = ANSWERS["cases"]["repeat"]
    it = client_as("a")
    reports = [_upload(it, CASES / u)["report"] for u in case["uploads"]]
    assert [r["events"]["already_there"] for r in reports] == case["events_already_there"]
    assert _events(world) == case["events_after"]
    _is_plant_a(world, it)


@history
def test_the_whole_export_twice_is_the_same_as_once(
    world: World, client_as: Callable[[str], TestClient]
) -> None:
    case = ANSWERS["cases"]["whole_twice"]
    it = client_as("a")
    reports = [_upload(it, CLEAN)["report"] for _ in case["uploads"]]
    assert [r["events"]["already_there"] for r in reports] == case["events_already_there"]
    assert _events(world) == case["events_after"]
    _is_plant_a(world, it)


@deletes
def test_deleting_the_second_upload_gives_the_first_uploads_answer(
    world: World, client_as: Callable[[str], TestClient]
) -> None:
    case = ANSWERS["cases"]["split"]
    alone = client_as("b")  # tenant B has its own PLANT-1: the first upload on its own
    _upload(alone, CASES / case["uploads"][0])
    it = client_as("a")
    _, second = (_upload(it, CASES / u) for u in case["uploads"])
    assert it.delete(f"/imports/{second['import_id']}").status_code == 204
    assert _events(world) == case["after_deleting_upload_2"]["events_after"] == _events(world, "b")
    want = _busy(world, "b")
    assert want and _busy(world) == pytest.approx(want, abs=0.01)


@fixes
def test_rows_fixed_in_the_app_give_the_answer_of_a_corrected_file(
    world: World, client_as: Callable[[str], TestClient]
) -> None:
    case = ANSWERS["cases"]["broken_rows_fixed_in_app"]
    it = client_as("a")
    (upload,) = (_upload(it, CASES / u) for u in case["uploads"])
    assert len(upload["report"]["import"]["row_errors"]) == case["rejected_rows"]
    for fix in case["fixes"]:
        made = it.post(
            f"/imports/{upload['import_id']}/corrections",
            json={**fix, "reason": "time typed wrong at the bench terminal"},
        )
        assert made.status_code == 201, made.text
    assert _events(world) == case["events_after_fixes"]
    _is_plant_a(world, it)
