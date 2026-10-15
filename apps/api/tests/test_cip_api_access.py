"""Who may open, see and decide what; only the COO changes it (sequence 10, task 03)."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from cip_api.auth.access import default_access
from cip_api.auth.roles import PAGES, START_PAGE, Decision, Role
from cip_api_testkit import PERSON_ROLES, World

pytestmark = pytest.mark.db
SignIn = Callable[..., TestClient]

# ADR-0007, decision table, row by row.
ADR_0007 = {
    "accept_exploit_subordinate": {"plant_director", "coo", "planner"},
    "approve_elevate": {"plant_director", "coo"},
    "release_expedite": {"planner", "shift_lead"},
    "report_stop": {"shift_lead", "station"},
    "edit_setup_calendar": {"planner", "it"},
    "import_run_diagnostic": {"planner", "it"},
    "sign_off_value": {"plant_director", "coo"},
    "manage_logins": {"it"},
    "change_access": {"coo"},
}


def test_defaults_follow_adr_0007() -> None:
    assert {d.value for d in Decision} == set(ADR_0007)
    for role in Role:
        access = default_access(role)
        assert access.pages == frozenset(PAGES), "default: every role opens every page"
        assert (access.money.value, access.plants.value) == ("eur", "all")
        assert {d.value for d in access.decisions} == {
            d for d, roles in ADR_0007.items() if role.value in roles
        }


def test_matrix_shows_defaults(sign_in: SignIn) -> None:
    body = sign_in("planner").get("/access").json()
    assert body["pages"] == list(PAGES)
    by_role = {r["role"]: r for r in body["roles"]}
    assert set(by_role) == {r.value for r in Role}
    assert by_role["shift_lead"]["start_page"] == START_PAGE[Role.SHIFT_LEAD]
    assert set(body["locked_decisions"]) == {"manage_logins", "change_access"}
    assert "access" in body["locked_pages"]["coo"]


@pytest.mark.parametrize("role", [*PERSON_ROLES, "station"])
def test_only_the_coo_changes_access(role: str, sign_in: SignIn) -> None:
    client = sign_in(role)
    expected = 200 if role == "coo" else 403
    page = {"role": "planner", "page": "value", "allowed": False}
    data = {"role": "planner", "money": "hours", "plants": "own"}
    decision = {"role": "planner", "decision": "approve_elevate", "allowed": True}
    assert client.put("/access/pages", json=page).status_code == expected
    assert client.put("/access/data", json=data).status_code == expected
    assert client.put("/access/decisions", json=decision).status_code == expected


def test_changes_apply_and_are_audited(world: World, sign_in: SignIn) -> None:
    coo = sign_in("coo")
    coo.put("/access/pages", json={"role": "shift_lead", "page": "value", "allowed": False})
    coo.put("/access/data", json={"role": "shift_lead", "money": "hours", "plants": "own"})
    coo.put(
        "/access/decisions",
        json={"role": "shift_lead", "decision": "accept_exploit_subordinate", "allowed": True},
    )
    me = sign_in("shift_lead").get("/auth/me").json()
    assert "value" not in me["pages"]
    assert (me["money"], me["plants"]) == ("hours", "own")
    assert "accept_exploit_subordinate" in me["decisions"]
    with world.owner.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT action, target, detail FROM audit_log "
                "WHERE tenant_id = :t AND action LIKE 'access_%' ORDER BY id"
            ),
            {"t": world.a},
        ).all()
    assert [tuple(r) for r in rows] == [
        ("access_page_changed", "shift_lead/value", "True -> False"),
        ("access_data_changed", "shift_lead", "money eur -> hours, plants all -> own"),
        ("access_decision_changed", "shift_lead/accept_exploit_subordinate", "False -> True"),
    ]


def test_changes_stay_in_the_tenant(sign_in: SignIn) -> None:
    sign_in("coo", "a").put(
        "/access/pages", json={"role": "planner", "page": "value", "allowed": False}
    )
    assert "value" in sign_in("planner", "b").get("/auth/me").json()["pages"]


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/access/pages", {"role": "planner", "page": "planner", "allowed": False}),
        ("/access/pages", {"role": "coo", "page": "access", "allowed": False}),
        ("/access/pages", {"role": "it", "page": "users", "allowed": False}),
        ("/access/decisions", {"role": "planner", "decision": "manage_logins", "allowed": True}),
        ("/access/decisions", {"role": "coo", "decision": "change_access", "allowed": False}),
    ],
    ids=["start-page", "coo-access", "it-users", "logins-it-only", "access-coo-only"],
)
def test_locked_entries_cannot_change(path: str, body: dict[str, object], sign_in: SignIn) -> None:
    assert sign_in("coo").put(path, json=body).status_code == 409


def test_unknown_values_are_rejected(sign_in: SignIn) -> None:
    coo = sign_in("coo")
    assert (
        coo.put(
            "/access/pages", json={"role": "planner", "page": "nope", "allowed": False}
        ).status_code
        == 422
    )
    bad_money = {"role": "planner", "money": "dollars", "plants": "all"}
    assert coo.put("/access/data", json=bad_money).status_code == 422
