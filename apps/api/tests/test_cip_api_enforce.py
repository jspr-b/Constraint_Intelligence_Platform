"""Every endpoint respects the access model, per role (sequence 10, task 04)."""

import re
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from cip_api.figures import money_out
from cip_api.main import create_app
from cip_api.settings import Settings
from cip_api_testkit import PERSON_ROLES, make_client
from constraint_engine.figure import Figure

SignIn = Callable[..., TestClient]
ALL_ROLES = [*PERSON_ROLES, "station"]
PUBLIC = {
    "/health",
    "/meta",
    "/auth/dev-login",
    "/auth/oidc-login",
    "/auth/station-login",
    "/auth/logout",
}
LOSS = Figure(value=4_100_000, unit="eur_cents", formula_id="test_loss_v1")
RATE = Figure(value=205_000, unit="eur_cents_per_h", formula_id="test_rate_v1")


def test_every_other_endpoint_needs_a_session() -> None:
    client = make_client(Settings(env="production"))
    paths = create_app(Settings()).openapi()["paths"]
    checked = 0
    for template, operations in paths.items():
        if template in PUBLIC:
            continue
        path = re.sub(r"\{[^}]+\}", "00000000-0000-0000-0000-000000000000", template)
        for method in operations:
            response = client.request(method.upper(), path, json={})
            assert response.status_code == 401, f"{method} {template}"
            checked += 1
    assert checked >= 15


@pytest.mark.db
@pytest.mark.parametrize("role", ALL_ROLES)
def test_page_access_per_role(role: str, sign_in: SignIn) -> None:
    client = sign_in(role)
    assert client.get("/plants/PLANT-1/summary").status_code == 200
    sign_in("coo").put("/access/pages", json={"role": role, "page": "data", "allowed": False})
    assert client.get("/plants/PLANT-1/summary").status_code == 403


@pytest.mark.db
@pytest.mark.parametrize("role", ALL_ROLES)
def test_decision_per_role(role: str, sign_in: SignIn) -> None:
    """Managing logins is IT's decision: everyone else gets 403 on the same call."""
    body = {"email": f"x-{role}@a.example.test", "role": "planner"}
    assert sign_in(role).post("/users", json=body).status_code == (201 if role == "it" else 403)


@pytest.mark.db
@pytest.mark.parametrize("role", ALL_ROLES)
def test_own_plant_per_role(role: str, sign_in: SignIn) -> None:
    client = sign_in(role)
    assert {p["plant_code"] for p in client.get("/plants").json()} == {"PLANT-1", "PLANT-2"}
    sign_in("coo").put("/access/data", json={"role": role, "money": "eur", "plants": "own"})
    assert [p["plant_code"] for p in client.get("/plants").json()] == ["PLANT-1"]
    assert client.get("/plants/PLANT-1/summary").status_code == 200
    assert client.get("/plants/PLANT-2/summary").status_code == 403


@pytest.mark.db
@pytest.mark.parametrize("role", ALL_ROLES)
def test_money_view_per_role(role: str, sign_in: SignIn) -> None:
    """Default €; once the COO sets hours, the same € Figure shows as constraint hours."""
    client = sign_in(role)
    shown = money_out(LOSS, client.get("/auth/me").json()["money"], RATE)
    assert (shown.value, shown.unit) == (4_100_000, "eur_cents")
    sign_in("coo").put("/access/data", json={"role": role, "money": "hours", "plants": "all"})
    shown = money_out(LOSS, client.get("/auth/me").json()["money"], RATE)
    assert (shown.value, shown.unit, shown.formula_id) == (20.0, "h", "constraint_hours_v1")
    assert shown.inputs["amount_eur_cents"]["value"] == 4_100_000


def test_hours_without_a_rate_is_missing() -> None:
    shown = money_out(LOSS, "hours")
    assert shown.unit == "h" and shown.confidence == "none"
    assert not isinstance(shown.value, int | float)
