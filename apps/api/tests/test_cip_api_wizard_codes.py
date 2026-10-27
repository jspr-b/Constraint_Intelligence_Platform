"""Mapping wizard, codes and formats (ADR-0011 §4, CI0005 seq 04): the plant's codes get a
meaning, dates and numbers are read from the values, the client answers what is unclear, names
steps, and confirms."""

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_cip_api_wizard_columns import FakeProvider, Files, _case, _client

from cip_api_testkit import World

pytestmark = pytest.mark.db

STEPS = "Code;Omschrijving\nLAS1;Welding\nLAK1;Paint\nMONT;Assembly\n"
SHIFTS = "Werkplek;Type;Start;Einde\n" + "".join(
    f"{c};Dienst;0{d}-08-2026 06:00;0{d}-08-2026 14:00\n"
    for d in range(1, 8)
    for c in ("LAS1", "LAK1")
)


def _small(log_days: range = range(1, 10)) -> Files:
    """An export whose dates are all day 1-9: day-month or month-day cannot be told."""
    rows = ["Werkplek;Bon;Status;Tijdstip;Aantal"]
    for i in range(60):
        day = log_days[i % len(log_days)]
        status = ["GESTART", "GEREED"][i % 2]
        rows.append(f"{['LAS1', 'LAK1'][i % 2]};{24000 + i // 2};{status};0{day}-08-2026 06:00;3")
    files = {"scans.csv": "\n".join(rows) + "\n", "werkplekken.csv": STEPS, "rooster.csv": SHIFTS}
    return [("files", (n, t.encode(), "text/csv")) for n, t in files.items()]


def _codes(body: dict[str, Any], target: str) -> dict[str, dict[str, Any]]:
    return {c["code"]: c for c in body["recognised"]["codes"] if c["target"] == target}


def _put(client: TestClient, i: str, what: str, body: dict[str, Any]) -> dict[str, Any]:
    response = client.put(f"/imports/{i}/{what}", json=body)
    assert response.status_code == 200, response.text
    out: dict[str, Any] = response.json()
    return out


def test_sap_codes_get_a_meaning_and_shortened_ones_are_asked(world: World, tmp_path: Path) -> None:
    client = _client(world, tmp_path)
    body = client.post("/plants/PLANT-1/imports", files=_case("sap_de")).json()
    i, found = body["import_id"], body["recognised"]
    events = _codes(body, "events.event_type")
    assert (events["ENDE"]["meaning"], events["ENDE"]["question"]) == ("end", False)
    assert (events["ANK"]["meaning"], events["ANK"]["sure"], events["ANK"]["question"]) == (
        "scan",
        "likely",
        True,
    )
    assert events["ANK"]["rows"] == 2108
    assert _codes(body, "orders.status")["ERÖF"]["meaning"] == "open"
    assert found["meanings"]["events.event_type"][0] == "start"
    assert found["code_questions"] == 6  # ANK, AUSS and the four one-letter start/end pairs
    refused = client.post(f"/imports/{i}/mapping/confirm")
    assert (refused.status_code, refused.json()["code"]) == (409, "mapping_not_ready")
    wrong = client.put(
        f"/imports/{i}/codes",
        json={"target": "events.event_type", "code": "ANK", "meaning": "shipped"},
    )
    assert (wrong.status_code, wrong.json()["code"]) == (422, "meaning_not_allowed")
    gone = client.put(
        f"/imports/{i}/codes", json={"target": "events.event_type", "code": "X", "meaning": "end"}
    )
    assert gone.json()["code"] == "code_not_found"
    for code, meaning in events.items():
        if meaning["question"]:
            body = _put(
                client,
                i,
                "codes",
                {"target": "events.event_type", "code": code, "meaning": meaning["meaning"]},
            )
    assert body["recognised"]["code_questions"] == 0
    assert _codes(body, "events.event_type")["ANK"]["source"] == "client"
    confirmed = client.post(f"/imports/{i}/mapping/confirm")
    assert confirmed.status_code == 200, confirmed.text


def test_a_code_left_out_is_said_and_never_silent(world: World, tmp_path: Path) -> None:
    client = _client(world, tmp_path)
    body = client.post(
        "/plants/PLANT-1/imports", files=_case("exact_en", {"REJECTED": "XQ7"})
    ).json()
    code = _codes(body, "events.event_type")["XQ7"]
    assert (code["meaning"], code["sure"], code["question"]) == (None, None, True)
    after = _put(
        client,
        body["import_id"],
        "codes",
        {"target": "events.event_type", "code": "XQ7", "meaning": "skip"},
    )
    code = _codes(after, "events.event_type")["XQ7"]
    assert (code["skipped"], code["question"], code["meaning"]) == (True, False, None)


def test_the_date_order_is_asked_once_when_the_values_cannot_tell(
    world: World, tmp_path: Path
) -> None:
    client = _client(world, tmp_path)
    body = client.post("/plants/PLANT-1/imports", files=_small()).json()
    formats = body["recognised"]["formats"]
    assert formats["date_order_question"] and body["recognised"]["format_questions"] == 1
    assert formats["date_example"] == "01-08-2026 06:00"
    assert formats["date_readings"] == {"day": "2026-08-01T06:00", "month": "2026-01-08T06:00"}
    assert formats["timezone"] == "Europe/Amsterdam"
    assert all(t["format"] is None for t in formats["times"])
    after = _put(client, body["import_id"], "formats", {"date_order": "day"})
    formats = after["recognised"]["formats"]
    assert not formats["date_order_question"] and after["recognised"]["format_questions"] == 0
    scans = next(t for t in formats["times"] if t["table"] == "scans.csv")
    assert (scans["format"], scans["sure"]) == ("%d-%m-%Y %H:%M", "confirmed")
    assert scans["example_read"] == "2026-08-01T06:00"
    month = _put(client, body["import_id"], "formats", {"date_order": "month"})
    scans = next(t for t in month["recognised"]["formats"]["times"] if t["table"] == "scans.csv")
    assert scans["example_read"] == "2026-01-08T06:00"


def test_a_day_above_12_needs_no_question(world: World, tmp_path: Path) -> None:
    client = _client(world, tmp_path)
    found = client.post("/plants/PLANT-1/imports", files=_case("mes_us")).json()["recognised"]
    assert found["format_questions"] == 0
    times = {(t["table"], t["column"]): t for t in found["formats"]["times"]}
    shift = times[("schedule.csv", "Begins")]
    assert (shift["format"], shift["example"], shift["example_read"]) == (
        "%m/%d/%Y %H:%M",
        "07/20/2026 06:00",
        "2026-07-20T06:00",
    )


def test_decimal_unit_and_step_answers(world: World, tmp_path: Path) -> None:
    client = _client(world, tmp_path)
    body = client.post("/plants/PLANT-1/imports", files=_case("ridder_hours")).json()
    i, formats = body["import_id"], body["recognised"]["formats"]
    assert (formats["decimal"], formats["decimal_question"]) == (",", False)
    assert formats["no_words"] == ["nee"]
    unit = next(u for u in formats["units"] if u["column"] == "Duur (min)")
    assert (unit["unit"], unit["sure"]) == ("min", "sure")
    after = _put(
        client, i, "formats", {"table": unit["table"], "column": "Duur (min)", "unit": "h"}
    )
    unit = next(u for u in after["recognised"]["formats"]["units"] if u["column"] == "Duur (min)")
    assert (unit["unit"], unit["sure"]) == ("h", "confirmed")
    steps = {s["code"]: s for s in after["recognised"]["steps"]}
    assert steps["SNIJ1"]["name"] == "Laser cutting" and steps["SNIJ1"]["kind"] is None
    named = _put(client, i, "steps", {"code": "SNIJ1", "kind": "machine"})
    step = next(s for s in named["recognised"]["steps"] if s["code"] == "SNIJ1")
    assert (step["name"], step["kind"], step["changed"]) == ("Laser cutting", "machine", True)
    renamed = _put(client, i, "steps", {"code": "SNIJ1", "name": "Laser 1"})
    step = next(s for s in renamed["recognised"]["steps"] if s["code"] == "SNIJ1")
    assert (step["code"], step["name"], step["kind"]) == ("SNIJ1", "Laser 1", "machine")
    missing = client.put(f"/imports/{i}/steps", json={"code": "CUT-01", "kind": "machine"})
    assert missing.json()["code"] == "step_not_found"
    empty = client.put(f"/imports/{i}/formats", json={})
    assert empty.json()["code"] == "no_answer"
    blank = client.put(f"/imports/{i}/steps", json={"code": "SNIJ1", "name": "   "})
    assert blank.json()["code"] == "no_answer"


def test_answers_stay_when_the_upload_is_read_again(world: World, tmp_path: Path) -> None:
    client = _client(world, tmp_path)
    body = client.post("/plants/PLANT-1/imports", files=_small()).json()
    i = body["import_id"]
    _put(client, i, "formats", {"date_order": "day"})
    _put(client, i, "steps", {"code": "LAS1", "kind": "machine"})
    # Naming a table reads the upload again: the answers about formats and steps stay.
    again = _put(client, i, "tables", {"table": "werkplekken.csv", "role": "steps"})
    assert again["recognised"]["formats"]["date_order"] == "day"
    assert next(s for s in again["recognised"]["steps"] if s["code"] == "LAS1")["kind"] == (
        "machine"
    )


def test_ai_suggests_a_code_meaning_and_it_stays_a_question(world: World, tmp_path: Path) -> None:
    fake = FakeProvider(
        {
            "suggestions": [
                {
                    "field": "events.event_type",
                    "code": "BEGUN_X",
                    "meaning": "start",
                    "certainty": "likely",
                    "reason": "BEGUN sounds like the work started.",
                },
                {"field": "events.event_type", "code": "BEGUN_X", "meaning": "launch"},
            ]
        }
    )
    client = _client(world, tmp_path, fake)
    body = client.post(
        "/plants/PLANT-1/imports", files=_case("exact_en", {"STARTED": "BEGUN_X"})
    ).json()
    code = _codes(body, "events.event_type")["BEGUN_X"]
    assert (code["meaning"], code["source"], code["question"]) == ("start", "ai", True)
    assert code["ai_reason"] == "BEGUN sounds like the work started."
    sent = [json.loads(p) for p in fake.prompts if '"codes"' in p]
    assert len(sent) == 1
    (column,) = sent[0]["codes"]
    assert set(column) == {"table", "column", "field", "codes", "meanings"}
    assert column["codes"] == ["BEGUN_X"] and len(column["codes"]) <= 5
    everything = " ".join(fake.prompts)
    assert "TEST-MEDEWERKER" not in everything and "PLANT-1" not in everything
