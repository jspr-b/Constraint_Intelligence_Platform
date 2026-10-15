"""Accounts managed by IT, with an audit trail (sequence 10, task 02)."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError

from cip_api.settings import get_settings
from cip_api_testkit import PERSON_ROLES, World, make_client

pytestmark = pytest.mark.db
SignIn = Callable[..., TestClient]


def _actions(world: World) -> list[str]:
    with world.owner.connect() as conn:
        return list(
            conn.execute(
                text("SELECT action FROM audit_log WHERE tenant_id = :t ORDER BY id"),
                {"t": world.a},
            ).scalars()
        )


@pytest.mark.parametrize("role", [*PERSON_ROLES, "station"])
def test_only_it_manages_logins(role: str, sign_in: SignIn) -> None:
    body = {"email": f"{role}-invitee@a.example.test", "role": "planner"}
    response = sign_in(role).post("/users", json=body)
    assert response.status_code == (201 if role == "it" else 403)


def test_invite_lists_and_audits(world: World, sign_in: SignIn) -> None:
    it = sign_in("it")
    body = {"email": "New.Planner@a.example.test", "role": "planner", "plant_code": "PLANT-1"}
    created = it.post("/users", json=body).json()
    assert created["email"] == "new.planner@a.example.test" and created["status"] == "invited"
    assert it.post("/users", json=body).status_code == 409
    emails = {u["email"] for u in it.get("/users").json()["users"]}
    assert "new.planner@a.example.test" in emails
    entries = it.get("/audit").json()
    assert entries[0]["action"] == "user_invited"
    assert entries[0]["target"] == f"user:{created['user_id']}"
    assert entries[0]["actor"].startswith("user:")


@pytest.mark.parametrize(
    "body",
    [
        {"email": "not-an-email", "role": "planner"},
        {"email": "screen@a.example.test", "role": "station"},
        {"email": "x@a.example.test", "role": "operator"},
        {"email": "x@a.example.test", "role": "planner", "plant_code": "NO-SUCH-PLANT"},
    ],
    ids=["bad-email", "station-is-not-a-person", "unknown-role", "unknown-plant"],
)
def test_invite_validation(body: dict[str, str], sign_in: SignIn) -> None:
    assert sign_in("it").post("/users", json=body).status_code == 422


def test_disable_ends_sessions_and_enable_restores(world: World, sign_in: SignIn) -> None:
    planner = sign_in("planner")
    it = sign_in("it")
    users = it.get("/users").json()["users"]
    planner_id = next(u["user_id"] for u in users if u["role"] == "planner")
    assert it.post(f"/users/{planner_id}/disable").json()["status"] == "disabled"
    assert planner.get("/auth/me").status_code == 401
    body = {"tenant_id": str(world.a), "email": world.email("planner")}
    assert make_client().post("/auth/dev-login", json=body).status_code == 401
    assert it.post(f"/users/{planner_id}/enable").json()["status"] == "active"
    assert make_client().post("/auth/dev-login", json=body).status_code == 204
    assert _actions(world)[-3:] == ["user_disabled", "user_enabled", "sign_in"]


def test_it_cannot_disable_itself(sign_in: SignIn) -> None:
    it = sign_in("it")
    me = it.get("/auth/me").json()["subject_id"]
    assert it.post(f"/users/{me}/disable").status_code == 409


def test_station_login_lifecycle(world: World, sign_in: SignIn) -> None:
    it = sign_in("it")
    with world.owner.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO resources (tenant_id, plant_code, resource_code, name, station_code) "
                "VALUES (:t, 'PLANT-1', 'WLD-02', 'Welding 2', 'ST-WLD')"
            ),
            {"t": world.a},
        )
    body = {"plant_code": "PLANT-1", "resource_code": "WLD-02", "pin": "7395"}
    created = it.post("/station-logins", json=body).json()
    assert created["status"] == "active" and "pin_hash" not in created
    assert it.post("/station-logins", json=body).status_code == 409
    bad = body | {"resource_code": "NOPE-9"}
    assert it.post("/station-logins", json=bad).status_code == 422
    assert it.post("/station-logins", json=body | {"pin": "12ab"}).status_code == 422

    login_id = created["station_login_id"]
    station = make_client()
    login = {"tenant_id": str(world.a), "plant_code": "PLANT-1", "resource_code": "WLD-02"}
    assert station.post("/auth/station-login", json=login | {"pin": "7395"}).status_code == 204
    assert it.post(f"/station-logins/{login_id}/disable").json()["status"] == "disabled"
    assert station.get("/auth/me").status_code == 401
    assert it.post(f"/station-logins/{login_id}/enable").json()["status"] == "active"
    assert it.post(f"/station-logins/{login_id}/pin", json={"pin": "5162"}).status_code == 200
    assert station.post("/auth/station-login", json=login | {"pin": "7395"}).status_code == 401
    assert station.post("/auth/station-login", json=login | {"pin": "5162"}).status_code == 204
    actions = _actions(world)
    for action in (
        "station_login_added",
        "station_login_disabled",
        "station_login_enabled",
        "station_pin_reset",
    ):
        assert action in actions


def test_station_logins_carry_no_person(world: World) -> None:
    with world.owner.connect() as conn:
        columns = set(
            conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'station_logins'"
                )
            ).scalars()
        )
    assert not columns & {"email", "user_id", "name", "operator", "employee", "badge"}


def test_audit_log_is_append_only_for_the_app(world: World) -> None:
    app = create_engine(get_settings().db_url())
    for sql in ("UPDATE audit_log SET detail = 'x'", "DELETE FROM audit_log"):
        with pytest.raises(ProgrammingError, match="permission denied"), app.begin() as conn:
            conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(world.a)})
            conn.execute(text(sql))
