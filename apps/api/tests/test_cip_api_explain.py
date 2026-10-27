"""Data problems explained (ADR-0011 §4, CI0005 seq 04): without AI the page shows the standard
explanation per reason; with AI, IT asks for an explanation and fix for its own export, which
is kept with the import and marked as the AI's. The AI sees reasons, file and column names and
at most 5 anonymised values; never personal columns, lines, counts or the plant."""

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_cip_api_wizard_columns import FakeProvider, _client

from cip_api_testkit import World

pytestmark = pytest.mark.db
DATA = Path(__file__).resolve().parents[3] / "data" / "synthetic"
BROKEN = DATA / "import_cases" / "broken" / "upload_1"
ANSWER = {
    "suggestions": [
        {
            "reason": "not_a_datetime",
            "explanation": "Some times in Tijdstip are text, not a date and time.",
            "fix": "Make the terminal export fill Tijdstip as day-month-year hours:minutes.",
        },
        {"reason": "invented", "explanation": "x", "fix": "y"},
    ]
}


def _broken(client: TestClient) -> str:
    files = [("files", (p.name, p.read_bytes(), "text/csv")) for p in sorted(BROKEN.iterdir())]
    i: str = client.post("/plants/PLANT-1/imports", files=files).json()["import_id"]
    assert client.post(f"/imports/{i}/run").status_code == 202
    return i


def test_without_ai_the_standard_explanations_stay_and_asking_says_why(
    world: World, tmp_path: Path
) -> None:
    client = _client(world, tmp_path)
    i = _broken(client)
    rows = client.get(f"/imports/{i}/rejected-rows").json()
    assert (rows["ai"], rows["ai_explanations"]) == ("not_connected", None)
    asked = client.post(f"/imports/{i}/rejected-rows/explain")
    assert (asked.status_code, asked.json()["code"]) == (409, "ai_not_connected")


def test_ai_explains_each_reason_and_sees_no_rows_or_people(world: World, tmp_path: Path) -> None:
    fake = FakeProvider(ANSWER)
    client = _client(world, tmp_path, fake)
    i = _broken(client)
    fake.prompts.clear()  # only the explanation call is checked here
    asked = client.post(f"/imports/{i}/rejected-rows/explain")
    assert asked.status_code == 200, asked.text
    out: dict[str, Any] = asked.json()
    assert out["state"] == "connected"
    assert [e["code"] for e in out["items"]] == ["not_a_datetime"]  # invented reason dropped
    assert out["items"][0]["fix"].startswith("Make the terminal export")
    (prompt,) = fake.prompts
    sent = json.loads(prompt)
    (problem,) = sent["problems"]
    assert set(problem) == {"reason", "needs", "columns", "examples"}
    assert problem["columns"] == [{"file": "mes_events.csv", "column": "Tijdstip"}]
    assert 0 < len(problem["examples"]) <= 5
    assert "not a time" not in prompt and "aaa a aaaa" in problem["examples"]
    for never in ("TEST-MEDEWERKER", "Medewerker", "PLANT-1", "6001"):
        assert never not in prompt
    # Kept with the import: the Import and Data quality pages show it.
    rows = client.get(f"/imports/{i}/rejected-rows").json()
    assert rows["ai"] == "connected"
    assert rows["ai_explanations"]["items"] == out["items"]
    quality = client.get("/plants/PLANT-1/data-quality").json()
    assert quality["ai_explanations"]["items"] == out["items"]
    assert quality["datetime_format"] == "20-07-2026 10:11"


def test_an_ai_error_keeps_the_standard_explanations(world: World, tmp_path: Path) -> None:
    client = _client(world, tmp_path, FakeProvider(fail=True))
    i = _broken(client)
    out = client.post(f"/imports/{i}/rejected-rows/explain").json()
    assert (out["state"], out["items"]) == ("error", [])
    assert client.get(f"/imports/{i}/rejected-rows").json()["ai_explanations"]["state"] == "error"


def test_the_ai_cost_limit_is_kept(world: World, tmp_path: Path) -> None:
    client = _client(world, tmp_path, FakeProvider(ANSWER), ai_max_eur_per_import=0.0)
    i = _broken(client)
    out = client.post(f"/imports/{i}/rejected-rows/explain").json()
    assert (out["state"], out["items"]) == ("limit_reached", [])


def test_a_role_that_cannot_fix_rows_cannot_ask(world: World, tmp_path: Path) -> None:
    client = _client(world, tmp_path, FakeProvider(ANSWER))
    i = _broken(client)
    body = {"tenant_id": str(world.a), "email": world.email("plant_director")}
    assert client.post("/auth/dev-login", json=body).status_code == 204
    assert client.post(f"/imports/{i}/rejected-rows/explain").status_code == 403
