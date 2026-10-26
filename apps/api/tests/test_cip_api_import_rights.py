"""Who may change import data (CI0004 seq 07): upload/run, fix rows, delete an import, delete all
plant data. Every endpoint checks its own right; a refusal names who can; the COO moves rights."""

import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from cip_api_testkit import World

pytestmark = pytest.mark.db
SignIn = Callable[..., TestClient]
ROLES = ("plant_director", "coo", "planner", "shift_lead", "station", "it")
FIX = {"file": "mes_events.csv", "line": 2, "column": "Tijdstip", "value": "x", "reason": "typo"}


def _calls(client: TestClient) -> dict[str, int]:
    """Each action on an import that does not exist: allowed roles get past the check (404/422),
    refused roles stop at it (403)."""
    missing = uuid.uuid4()
    return {
        "run": client.post(f"/imports/{missing}/run").status_code,
        "fix": client.post(f"/imports/{missing}/corrections", json=FIX).status_code,
        "delete": client.delete(f"/imports/{missing}").status_code,
        "delete_all": client.delete("/plants/PLANT-1/data?confirm=WRONG").status_code,
    }


@pytest.mark.parametrize("role", ROLES)
def test_default_rights_per_role(role: str, sign_in: SignIn) -> None:
    allowed = {
        "planner": {"run", "fix", "delete"},
        "it": {"run", "fix", "delete", "delete_all"},
    }.get(role, set())
    for action, status in _calls(sign_in(role)).items():
        assert (status != 403) == (action in allowed), (role, action, status)


def test_a_refusal_says_who_can(sign_in: SignIn) -> None:
    refused = sign_in("plant_director").delete(f"/imports/{uuid.uuid4()}")
    body = refused.json()
    assert (refused.status_code, body["code"]) == (403, "decision_not_allowed")
    assert body["message"] == (
        "Your role cannot delete imports. Ask Planner or IT / ERP owner; the COO decides who may."
    )
    everything = sign_in("planner").delete("/plants/PLANT-1/data?confirm=PLANT-1").json()
    assert everything["message"].startswith("Your role cannot delete all data of a plant. Ask IT")


def test_the_coo_moves_fixing_rows_to_it_only(world: World, sign_in: SignIn) -> None:
    coo = sign_in("coo")
    moved = coo.put(
        "/access/decisions", json={"role": "planner", "decision": "fix_rows", "allowed": False}
    )
    assert moved.status_code == 200, moved.text
    planner = sign_in("planner")
    assert "fix_rows" not in planner.get("/auth/me").json()["decisions"]
    refused = planner.post(f"/imports/{uuid.uuid4()}/corrections", json=FIX)
    assert refused.status_code == 403
    assert refused.json()["message"] == (
        "Your role cannot fix rows in the app. Ask IT / ERP owner; the COO decides who may."
    )
    assert _calls(planner)["delete"] != 403, "only fixing rows moved"
    assert sign_in("it").post(f"/imports/{uuid.uuid4()}/corrections", json=FIX).status_code != 403
    access = coo.get("/access").json()
    planner_row = next(r for r in access["roles"] if r["role"] == "planner")
    assert "fix_rows" not in planner_row["decisions"]
    assert {"fix_rows", "delete_import", "delete_plant_data"} <= set(access["decisions"])
