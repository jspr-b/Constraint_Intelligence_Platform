"""An import runs from the confirmed summary (ADR-0011, CI0005 seq 05): an export the app has no
format for is read the way the client confirmed it, and gives its plant's known answer with the
plant's own step codes. Without a confirmed summary, the run says what to do first."""

from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient
from test_cip_api_wizard_codes import _codes, _put
from test_cip_api_wizard_columns import _case, _client

from cip_api_testkit import World

pytestmark = pytest.mark.db
ROOT = Path(__file__).resolve().parents[3]
CASES = ROOT / "data" / "synthetic" / "wizard_cases"


def _answer_codes(client: TestClient, i: str, body: dict[str, Any]) -> dict[str, Any]:
    """Say yes to every code the app asks about."""
    for target in body["recognised"]["meanings"]:
        for code, found in _codes(body, target).items():
            if found["question"]:
                body = _put(
                    client,
                    i,
                    "codes",
                    {"target": target, "code": code, "meaning": found["meaning"]},
                )
    return body


def _confirmed_sap(client: TestClient) -> tuple[str, dict[str, Any]]:
    body = client.post("/plants/PLANT-1/imports", files=_case("sap_de")).json()
    i = body["import_id"]
    not_yet = client.post(f"/imports/{i}/run")
    assert (not_yet.status_code, not_yet.json()["code"]) == (409, "mapping_not_confirmed")
    body = _answer_codes(client, i, body)
    confirmed = client.post(f"/imports/{i}/mapping/confirm")
    assert confirmed.status_code == 200, confirmed.text
    return i, confirmed.json()


def test_an_unknown_export_runs_from_its_confirmed_summary(world: World, tmp_path: Path) -> None:
    client = _client(world, tmp_path)
    i, body = _confirmed_sap(client)
    assert body["mapping"] == "WIZARD"
    assert client.post(f"/imports/{i}/run").status_code == 202
    done = client.get(f"/imports/{i}").json()
    assert done["status"] == "done", done["error"]
    assert done["report"]["import"]["rows_written"]["events"] > 1000
    expected = yaml.safe_load((CASES / "sap_de" / "expected.yaml").read_text())
    answer = yaml.safe_load((ROOT / expected["plant_answer"]).read_text())
    own = {v: k for k, v in expected["code_tables"].get("resource", {}).items()}
    (found,) = client.get("/plants/PLANT-1/detection").json()["detections"]
    assert found["resource_code"] == own.get(answer["constraint"], answer["constraint"])
    assert found["kind"] == answer["constraint_kind"]


def test_the_summary_cannot_change_once_it_ran(world: World, tmp_path: Path) -> None:
    client = _client(world, tmp_path)
    i, body = _confirmed_sap(client)
    assert client.post(f"/imports/{i}/run").status_code == 202
    code = next(c for c in body["recognised"]["codes"] if c["target"] == "events.event_type")
    changed = client.put(
        f"/imports/{i}/codes",
        json={"target": code["target"], "code": code["code"], "meaning": "skip"},
    )
    assert (changed.status_code, changed.json()["code"]) == (409, "summary_in_use")


def test_an_answer_after_confirming_asks_to_confirm_again(world: World, tmp_path: Path) -> None:
    client = _client(world, tmp_path)
    i, body = _confirmed_sap(client)
    step = body["recognised"]["steps"][0]
    body = _put(client, i, "steps", {"code": step["code"], "name": "Laser 1", "kind": "machine"})
    assert body["recognised"]["confirmed"] is None
    again = client.post(f"/imports/{i}/run")
    assert (again.status_code, again.json()["code"]) == (409, "mapping_not_confirmed")


def test_hour_bookings_run_to_a_less_sure_answer_that_says_why(
    world: World, tmp_path: Path
) -> None:
    client = _client(world, tmp_path)
    body = client.post("/plants/PLANT-1/imports", files=_case("ridder_hours")).json()
    i = body["import_id"]
    assert {t["role"] for t in body["recognised"]["tables"]} >= {"hour_bookings"}
    body = _answer_codes(client, i, body)
    confirmed = client.post(f"/imports/{i}/mapping/confirm")
    assert confirmed.status_code == 200, confirmed.text
    assert client.post(f"/imports/{i}/run").status_code == 202
    done = client.get(f"/imports/{i}").json()
    assert done["status"] == "done", done["error"]
    (found,) = client.get("/plants/PLANT-1/detection").json()["detections"]
    assert (found["resource_code"], found["kind"]) == ("LAK1", "internal")  # plant A's PNT-01
    assert found["confidence"] != "high"
    assert {"code": "times_from_bookings", "values": {"share_pct": 100.0}} in found["reasons"]
