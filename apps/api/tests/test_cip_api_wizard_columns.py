"""Mapping wizard, step 2 (ADR-0011 §3-4, CI0005 seq 03): columns matched by rules, open
columns suggested by the AI within its privacy limits, the client answers and confirms."""

import json
import re
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from cip_api.ai import Reply, get_ai_provider
from cip_api.settings import Settings
from cip_api_testkit import World, make_client

pytestmark = pytest.mark.db
CASES = Path(__file__).resolve().parents[3] / "data" / "synthetic" / "wizard_cases"
Files = list[tuple[str, tuple[str, bytes, str]]]


class FakeProvider:
    """Answers like the AI would; only in tests. Records everything it was sent."""

    def __init__(self, answer: dict[str, Any] | None = None, fail: bool = False) -> None:
        self.answer = answer or {"suggestions": []}
        self.fail = fail
        self.prompts: list[str] = []

    def complete(self, system: str, prompt: str, max_tokens: int) -> Reply:
        self.prompts.append(prompt)
        if self.fail:
            raise TimeoutError("no answer")
        return Reply(json.dumps(self.answer), 900, 120)


def _client(
    world: World, tmp_path: Path, provider: FakeProvider | None = None, **kw: Any
) -> TestClient:
    client = make_client(Settings(env="dev", data_dir=tmp_path, run_jobs_inline=True, **kw))
    if provider is not None:
        cast(FastAPI, client.app).dependency_overrides[get_ai_provider] = lambda: provider
    body = {"tenant_id": str(world.a), "email": world.email("it")}
    assert client.post("/auth/dev-login", json=body).status_code == 204
    return client


def _case(name: str, rename: dict[str, str] | None = None) -> Files:
    out = []
    for f in sorted((CASES / name).iterdir()):
        if f.name == "expected.yaml":
            continue
        data = f.read_bytes()
        for old, new in (rename or {}).items():
            data = data.replace(old.encode(), new.encode())
        out.append(("files", (f.name, data, "application/octet-stream")))
    return out


def _columns(body: dict[str, Any], table: str) -> dict[str, dict[str, Any]]:
    return {c["column"]: c for c in body["recognised"]["columns"] if c["table"] == table}


def test_columns_are_matched_and_the_summary_is_confirmed(world: World, tmp_path: Path) -> None:
    client = _client(world, tmp_path)
    body = client.post("/plants/PLANT-1/imports", files=_case("exact_en")).json()
    found = body["recognised"]
    events = _columns(body, "ShopFloorEvents.csv")
    assert (events["Timestamp"]["fields"], events["Timestamp"]["sure"]) == (["events.at"], "sure")
    assert events["Employee"]["personal"] and events["Employee"]["fields"] == []
    assert found["column_questions"] == 0 and found["ai"]["state"] == "not_connected"
    assert "events.at" in found["fields"]["events"]
    i = body["import_id"]
    # Customers.csv is still open: nothing is confirmed while a question is open.
    refused = client.post(f"/imports/{i}/mapping/confirm")
    assert (refused.status_code, refused.json()["code"]) == (409, "mapping_not_ready")
    client.put(f"/imports/{i}/tables", json={"table": "Customers.csv", "role": "skip"})
    confirmed = client.post(f"/imports/{i}/mapping/confirm").json()["recognised"]["confirmed"]
    assert confirmed and confirmed["by"]
    # A later answer clears the confirmation: the client confirms what they see.
    after = client.put(
        f"/imports/{i}/columns",
        json={"table": "ShopFloorEvents.csv", "column": "Good qty", "field": "skip"},
    ).json()["recognised"]
    assert after["confirmed"] is None
    assert _columns({"recognised": after}, "ShopFloorEvents.csv")["Good qty"]["skipped"]


def test_a_column_answer_must_fit_the_table(world: World, tmp_path: Path) -> None:
    client = _client(world, tmp_path)
    i = client.post("/plants/PLANT-1/imports", files=_case("exact_en")).json()["import_id"]
    wrong = client.put(
        f"/imports/{i}/columns",
        json={"table": "ShopFloorEvents.csv", "column": "Timestamp", "field": "orders.due_at"},
    )
    assert (wrong.status_code, wrong.json()["code"]) == (422, "field_not_allowed")
    missing = client.put(
        f"/imports/{i}/columns",
        json={"table": "ShopFloorEvents.csv", "column": "Nope", "field": "events.at"},
    )
    assert missing.json()["code"] == "column_not_found"


def test_an_unclear_column_is_asked_and_the_client_answers(world: World, tmp_path: Path) -> None:
    client = _client(world, tmp_path)
    body = client.post(
        "/plants/PLANT-1/imports", files=_case("exact_en", {"Good qty": "Kolom 7"})
    ).json()
    col = _columns(body, "ShopFloorEvents.csv")["Kolom 7"]
    assert (col["fields"], col["sure"], col["question"]) == ([], None, True)
    after = client.put(
        f"/imports/{body['import_id']}/columns",
        json={
            "table": "ShopFloorEvents.csv",
            "column": "Kolom 7",
            "field": "events.quantity_units",
        },
    ).json()
    col = _columns(after, "ShopFloorEvents.csv")["Kolom 7"]
    assert (col["fields"], col["source"], col["question"]) == (
        ["events.quantity_units"],
        "client",
        False,
    )


def test_ai_suggests_an_open_column_and_it_stays_a_question(world: World, tmp_path: Path) -> None:
    fake = FakeProvider(
        {
            "suggestions": [
                {
                    "table": "ShopFloorEvents.csv",
                    "column": "Kolom 7",
                    "field": "events.quantity_units",
                    "certainty": "likely",
                    "reason": "Small whole numbers next to the finish events: a good count.",
                },
                # Not an allowed field, not an asked column: both dropped.
                {"table": "ShopFloorEvents.csv", "column": "Kolom 7", "field": "orders.due_at"},
                {"table": "Customers.csv", "column": "Country", "field": "events.at"},
            ]
        }
    )
    client = _client(world, tmp_path, fake)
    body = client.post(
        "/plants/PLANT-1/imports", files=_case("exact_en", {"Good qty": "Kolom 7"})
    ).json()
    col = _columns(body, "ShopFloorEvents.csv")["Kolom 7"]
    assert (col["fields"], col["source"], col["sure"], col["question"]) == (
        ["events.quantity_units"],
        "ai",
        "likely",
        True,
    )
    assert col["ai_reason"].startswith("Small whole numbers")
    assert body["recognised"]["ai"]["state"] == "connected"


def test_ai_payload_is_privacy_limited(world: World, tmp_path: Path) -> None:
    fake = FakeProvider()
    client = _client(world, tmp_path, fake)
    client.post(
        "/plants/PLANT-1/imports",
        files=_case("mes_us", {"Quantity": "Kolom 7", "Due Date": "Kolom 8"}),
    )
    assert len(fake.prompts) == 1
    sent = json.loads(fake.prompts[0])
    assert set(sent) == {"columns"}
    asked = {(c["table"], c["column"]) for c in sent["columns"]}
    # Only the columns the rules could not match; never a matched or personal column.
    assert ("labor_transactions.csv", "Kolom 7") in asked
    assert all(
        c["column"] not in ("Badge", "Work Center", "Transaction Time") for c in sent["columns"]
    )
    for c in sent["columns"]:
        assert set(c) == {"table", "table_holds", "column", "examples", "fields"}
        assert len(c["examples"]) <= 5
        # Examples are shapes only: no letter but a/A, no digit but 9.
        assert all(not re.search(r"[b-zB-Z0-8]", e) for e in c["examples"])
    text = fake.prompts[0]
    assert "TEST-OP" not in text and "PLANT-1" not in text and "JOB-24" not in text
    assert world.email("it") not in text and str(world.a) not in text
    assert len(text) < 20_000


def test_ai_error_and_limit_fall_back_to_rules(world: World, tmp_path: Path) -> None:
    files = _case("exact_en", {"Good qty": "Kolom 7"})
    failing = _client(world, tmp_path / "a", FakeProvider(fail=True))
    body = failing.post("/plants/PLANT-1/imports", files=files).json()
    assert body["recognised"]["ai"]["state"] == "error"
    assert _columns(body, "ShopFloorEvents.csv")["Timestamp"]["fields"] == ["events.at"]

    fake = FakeProvider()
    capped = _client(world, tmp_path / "b", fake, ai_max_eur_per_import=0.0)
    body = capped.post("/plants/PLANT-1/imports", files=files).json()
    assert body["recognised"]["ai"]["state"] == "limit_reached" and fake.prompts == []
    assert _columns(body, "ShopFloorEvents.csv")["Kolom 7"]["question"]


def test_running_app_has_no_ai_without_a_key() -> None:
    assert get_ai_provider(Settings(env="dev")) is None


def test_ai_spend_adds_up_when_the_upload_is_read_again(world: World, tmp_path: Path) -> None:
    fake = FakeProvider()
    client = _client(world, tmp_path, fake)
    files = _case("exact_en", {"Good qty": "Kolom 7"})
    i = client.post("/plants/PLANT-1/imports", files=files).json()["import_id"]
    # Naming a table reads the upload again: the AI is asked again and its cost is added.
    client.put(f"/imports/{i}/tables", json={"table": "Customers.csv", "role": "skip"})
    assert len(fake.prompts) == 2
    with world.owner.connect() as db:
        spent = db.execute(
            text("SELECT (wizard->'ai'->>'spent_eur')::float FROM imports WHERE import_id = :i"),
            {"i": i},
        ).scalar_one()
    one = 900 / 1e6 * 3.0 + 120 / 1e6 * 15.0
    assert spent == pytest.approx(2 * one, abs=1e-4)
