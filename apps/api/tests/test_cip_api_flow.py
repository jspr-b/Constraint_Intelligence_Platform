"""The flow found in the data: built by the facts job after every upload, served per plant."""

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import text

from cip_api.settings import Settings
from cip_api_testkit import World, make_client

pytestmark = pytest.mark.db
DATA = Path(__file__).resolve().parents[3] / "data" / "synthetic"
EXPORT = DATA / "plant_a" / "erp_export"
KNOWN = yaml.safe_load((DATA / "wizard_cases" / "exact_en" / "expected.yaml").read_text())["flow"]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(env="dev", data_dir=tmp_path, run_jobs_inline=True)


def _login(world: World, settings: Settings, role: str, tenant: str = "a") -> TestClient:
    client = make_client(settings)
    body = {"tenant_id": str(getattr(world, tenant)), "email": world.email(role, tenant)}
    assert client.post("/auth/dev-login", json=body).status_code == 204
    return client


def _import(it: TestClient) -> str:
    folder = EXPORT / "clean" / "csv"
    files = [("files", (f.name, f.read_bytes(), "text/csv")) for f in sorted(folder.iterdir())]
    body = it.post("/plants/PLANT-1/imports", files=files).json()
    assert it.post(f"/imports/{body['import_id']}/run").status_code == 202
    return str(body["import_id"])


def test_before_any_upload_the_flow_is_empty(world: World, settings: Settings) -> None:
    body = _login(world, settings, "planner").get("/plants/PLANT-1/flow").json()
    assert body["jobs"] == 0 and body["routes"] == [] and body["run"] is None


def test_an_upload_finds_the_known_flow_with_every_share_explained(
    world: World, settings: Settings
) -> None:
    it = _login(world, settings, "it")
    import_id = _import(it)
    body = _login(world, settings, "planner").get("/plants/PLANT-1/flow").json()
    assert body["import_id"] == import_id and body["run"]["status"] == "ready"
    assert body["jobs"] == KNOWN["jobs"]
    assert [(r["steps"], r["jobs"], r["share"]["value"]) for r in body["routes"]] == [
        (r["steps"], r["jobs"], r["share_pct"]) for r in KNOWN["routes"]
    ]
    assert body["other_routes_jobs"] == KNOWN["other_routes_jobs"]
    share = body["routes"][0]["share"]
    assert share["formula_id"] == "flow_share_pct_v1"
    assert share["inputs"] == {
        "jobs_this_way": KNOWN["routes"][0]["jobs"],
        "jobs_counted": KNOWN["jobs"],
    }
    assert share["period_start_at"] and share["period_end_at"]
    assert {(a["from_step"], a["to_step"], a["jobs"]) for a in body["arrows"]} == {
        (a["from"], a["to"], a["jobs"]) for a in KNOWN["arrows"]
    }


def test_other_tenants_see_nothing(world: World, settings: Settings) -> None:
    _import(_login(world, settings, "it"))
    body = _login(world, settings, "it", "b").get("/plants/PLANT-1/flow").json()
    assert body["jobs"] == 0


def _edits(**doc: object) -> dict[str, object]:
    return {"edits": doc, "version": 0, "change": "test"}


def test_flow_edits_are_saved_logged_and_used_by_the_calculation(
    world: World, settings: Settings
) -> None:
    it = _login(world, settings, "it")
    _import(it)
    step = {
        "code": "NEW-01",
        "name": "Visual check",
        "kind": "check",
        "after": "PNT-01",
        "before": "ASM-01",
    }
    saved = it.put(
        "/plants/PLANT-1/flow/edits",
        json=_edits(
            steps_added=[step],
            parallel=[{"code": "ASM-01", "places": 3}],
            routes_wrong=[{"from_step": "CUT-01", "to_step": "PCK-01"}],
        ),
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["version"] == 1 and saved.json()["updated_by_role"] == "it"
    body = it.get("/plants/PLANT-1/flow").json()
    arrows = {(a["from_step"], a["to_step"]): a for a in body["edited_arrows"]}
    assert arrows[("PNT-01", "ASM-01")]["hidden"]
    added = arrows[("PNT-01", "NEW-01")]
    assert added["added"] and not added["measured"] and added["assumed_jobs"] == 328
    assert added["assumed_share"]["formula_id"] == "flow_share_pct_v1"
    assert arrows[("CUT-01", "PCK-01")]["wrong"]
    with world.owner.connect() as conn:
        logged = (
            conn.execute(
                text("SELECT action FROM audit_log WHERE tenant_id = :t AND action LIKE 'flow:%'"),
                {"t": world.a},
            )
            .scalars()
            .all()
        )
    assert logged == ["flow:test"]
    # A save on an older version is refused with a plain message.
    stale = it.put("/plants/PLANT-1/flow/edits", json=_edits())
    assert stale.status_code == 409


def test_roles_without_setup_rights_cannot_edit_the_flow(world: World, settings: Settings) -> None:
    _import(_login(world, settings, "it"))
    coo = _login(world, settings, "coo")
    refused = coo.put("/plants/PLANT-1/flow/edits", json=_edits())
    assert refused.status_code == 403
    assert "Planner" in refused.json()["detail"] or "IT" in refused.json()["detail"]
    assert coo.get("/plants/PLANT-1/flow/edits").json()["version"] == 0
