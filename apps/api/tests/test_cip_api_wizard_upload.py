"""Mapping wizard, step 1 (ADR-0011 §2, CI0005 seq 02): the whole export in one upload, each
table's role and the links, and the client naming or skipping what the app cannot place."""

import io
import json
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import text

from cip_api.settings import Settings
from cip_api.wizard import clean_name
from cip_api_testkit import World, make_client

pytestmark = pytest.mark.db
CASES = Path(__file__).resolve().parents[3] / "data" / "synthetic" / "wizard_cases"
Files = list[tuple[str, tuple[str, bytes, str]]]


@pytest.fixture
def client_as(world: World, tmp_path: Path) -> Callable[[str], TestClient]:
    settings = Settings(env="dev", data_dir=tmp_path, run_jobs_inline=True)

    def _client(role: str) -> TestClient:
        client = make_client(settings)
        body = {"tenant_id": str(world.a), "email": world.email(role)}
        assert client.post("/auth/dev-login", json=body).status_code == 204
        return client

    return _client


def _case(name: str) -> Files:
    return [
        ("files", (f.name, f.read_bytes(), "application/octet-stream"))
        for f in sorted((CASES / name).iterdir())
        if f.name != "expected.yaml"
    ]


def _roles(body: dict[str, Any]) -> dict[str, tuple[str | None, str | None]]:
    return {t["table"]: (t["role"], t["sure"]) for t in body["recognised"]["tables"]}


def test_a_whole_unseen_export_is_sorted_and_linked(client_as: Callable[[str], TestClient]) -> None:
    created = client_as("it").post("/plants/PLANT-1/imports", files=_case("exact_en"))
    assert created.status_code == 201, created.text
    found = created.json()["recognised"]
    roles = _roles(created.json())
    assert roles["ShopFloorEvents.csv"] == ("events", "sure")
    assert roles["Resources.csv"] == ("steps", "sure")
    assert roles["Roster.csv"] == ("calendar", "sure")
    assert roles["Customers.csv"] == (None, None)
    assert {m["key"]: m["tables"] for m in found["minimum"]} == {
        "events": ["ShopFloorEvents.csv"],
        "steps": ["Resources.csv"],
        "calendar": ["Roster.csv"],
    }
    assert found["to_answer"] == ["Customers.csv"]
    assert {
        "table": "ShopFloorEvents.csv",
        "column": "Resource",
        "to_table": "Resources.csv",
        "to_column": "Resource",
        "found": 6,
        "total": 6,
        "is_list": False,
    } in found["links"]
    events = next(t for t in found["tables"] if t["table"] == "ShopFloorEvents.csv")
    assert events["personal_columns"] == 1 and events["rows"] == 7084


def test_personal_values_are_never_stored(
    client_as: Callable[[str], TestClient], world: World
) -> None:
    client_as("it").post("/plants/PLANT-1/imports", files=_case("mes_us"))
    with world.owner.connect() as db:
        stored = (
            db.execute(
                text("SELECT wizard::text FROM imports WHERE tenant_id = :t"), {"t": world.a}
            )
            .scalars()
            .all()
        )
    # The name is listed so the summary can say it was not read; its values never are.
    assert stored and not any("TEST-OPERATOR" in s for s in stored)
    columns = [c for s in stored for c in json.loads(s)["columns"] if c["column"] == "Badge"]
    assert columns and all(c["personal"] and c["sure"] == "sure" for c in columns)


def test_a_zip_is_unpacked_and_what_is_not_a_table_is_listed(
    client_as: Callable[[str], TestClient],
) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for f in sorted((CASES / "sap_de").iterdir()):
            if f.name != "expected.yaml":
                z.writestr(f"export 2026/{f.name}", f.read_bytes())
        z.writestr("export 2026/read me.pdf", b"%PDF-1.4")
        z.writestr("__MACOSX/export 2026/._AFRU_Rueckmeldungen.txt", b"x")
    zipped = [("files", ("SAP export (Oct).zip", buf.getvalue(), "application/zip"))]
    body = client_as("it").post("/plants/PLANT-1/imports", files=zipped).json()
    assert len(body["file_names"]) == 10 and "AFRU_Rueckmeldungen.txt" in body["file_names"]
    assert body["recognised"]["not_read"] == [
        {"name": "read me.pdf", "problem": "not_a_table_file"}
    ]
    assert _roles(body)["AFRU_Rueckmeldungen.txt"][0] == "events"
    expected = yaml.safe_load((CASES / "sap_de" / "expected.yaml").read_text())["files"]
    assert len(expected) == len(body["recognised"]["tables"])


def test_a_workbook_gives_one_table_per_sheet(client_as: Callable[[str], TestClient]) -> None:
    body = client_as("it").post("/plants/PLANT-1/imports", files=_case("isah_xlsx")).json()
    assert _roles(body)["isah_export.xlsx#Terugmeldingen"] == ("events", "sure")
    assert len(body["recognised"]["tables"]) == 10


def test_names_are_cleaned_not_refused() -> None:
    assert clean_name("Shop Floor (1).CSV") == "Shop_Floor_1.csv"
    assert clean_name("C:\\exports\\rooster.xlsx") == "rooster.xlsx"
    assert clean_name("../../etc/passwd.csv") == "passwd.csv"
    assert clean_name("tool.exe") is None
    assert clean_name("no_suffix") is None


def test_the_client_names_or_skips_a_table(client_as: Callable[[str], TestClient]) -> None:
    it = client_as("it")
    upload = it.post("/plants/PLANT-1/imports", files=_case("exact_en")).json()
    url = f"/imports/{upload['import_id']}/tables"
    skipped = it.put(url, json={"table": "Customers.csv", "role": "skip"})
    assert skipped.status_code == 200, skipped.text
    customers = next(
        t for t in skipped.json()["recognised"]["tables"] if t["table"] == "Customers.csv"
    )
    assert (customers["skipped"], customers["sure"]) == (True, "confirmed")
    assert skipped.json()["recognised"]["to_answer"] == []
    named = it.put(url, json={"table": "Roster.csv", "role": "calendar"}).json()
    assert _roles(named)["Roster.csv"] == ("calendar", "confirmed")
    assert it.put(url, json={"table": "nope.csv", "role": "skip"}).status_code == 404
    assert it.put(url, json={"table": "Roster.csv", "role": "dinner"}).status_code == 422
    assert (
        client_as("planner").put(url, json={"table": "Roster.csv", "role": "skip"}).status_code
        == 200
    )
    assert (
        client_as("plant_director")
        .put(url, json={"table": "Roster.csv", "role": "skip"})
        .status_code
        == 403
    )


def test_answers_stay_when_a_file_is_removed(client_as: Callable[[str], TestClient]) -> None:
    it = client_as("it")
    upload = it.post("/plants/PLANT-1/imports", files=_case("exact_en")).json()
    it.put(
        f"/imports/{upload['import_id']}/tables", json={"table": "Customers.csv", "role": "skip"}
    )
    after = it.delete(f"/imports/{upload['import_id']}/files/Overtime.csv").json()
    assert "Overtime.csv" not in _roles(after)
    assert json.dumps(after["recognised"]["to_answer"]) == "[]"


def test_a_zip_that_unpacks_too_large_is_refused_and_leaves_nothing(
    world: World, tmp_path: Path
) -> None:
    # 3 MB of zeros packs to a few KB: the limit counts what is unpacked, not the zip.
    client = make_client(Settings(env="dev", data_dir=tmp_path, max_upload_mb=1))
    body = {"tenant_id": str(world.a), "email": world.email("it")}
    assert client.post("/auth/dev-login", json=body).status_code == 204
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("small.csv", b"a;b\n1;2\n")
        z.writestr("huge.csv", b"a;b\n" + b"0" * (3 * 1024 * 1024))
    assert len(buf.getvalue()) < 1024 * 1024
    zipped = [("files", ("export.zip", buf.getvalue(), "application/zip"))]
    response = client.post("/plants/PLANT-1/imports", files=zipped)
    assert response.status_code == 413
    assert response.json()["code"] == "file_too_large"
    assert not [p for p in tmp_path.rglob("*.csv")]
