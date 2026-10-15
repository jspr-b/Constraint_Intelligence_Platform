"""Sign-in, sign-out, expiry and tenant isolation (sequence 10, task 01)."""

import time
from collections.abc import Callable
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import text

from cip_api.auth import oidc
from cip_api.auth.sessions import COOKIE
from cip_api.settings import Settings
from cip_api_testkit import PIN, World, make_client

pytestmark = pytest.mark.db
SignIn = Callable[..., TestClient]


def test_session_gives_tenant_and_role(world: World, sign_in: SignIn) -> None:
    client = sign_in("planner")
    cookie = client.cookies.get(COOKIE)
    assert cookie and len(cookie) > 30
    me = client.get("/auth/me").json()
    assert me["tenant_id"] == str(world.a) and me["role"] == "planner"
    assert me["subject_type"] == "user" and me["start_page"] == "planner"
    # The session wins over a dev header that names another tenant and role.
    me = client.get("/auth/me", headers={"X-Tenant-Id": str(world.b), "X-Role": "coo"}).json()
    assert me["tenant_id"] == str(world.a) and me["role"] == "planner"


def test_only_the_token_hash_is_stored(world: World, sign_in: SignIn) -> None:
    token = sign_in("coo").cookies[COOKIE]
    with world.owner.connect() as conn:
        stored = (
            conn.execute(
                text("SELECT token_hash FROM sessions WHERE tenant_id = :t"), {"t": world.a}
            )
            .scalars()
            .all()
        )
    assert stored and token not in stored and all(len(h) == 64 for h in stored)


def test_sign_out_ends_the_session(sign_in: SignIn) -> None:
    client = sign_in("coo")
    token = client.cookies[COOKIE]
    assert client.post("/auth/logout").status_code == 204
    assert COOKIE not in client.cookies
    replay = make_client()
    replay.cookies.set(COOKIE, token)
    response = replay.get("/auth/me")
    assert (
        response.status_code == 401 and response.json()["detail"] == "session expired or signed out"
    )


def test_expired_session_is_refused(world: World, sign_in: SignIn) -> None:
    client = sign_in("coo")
    with world.owner.begin() as conn:
        conn.execute(
            text(
                "UPDATE sessions SET expires_at = now() - interval '1 minute' WHERE tenant_id = :t"
            ),
            {"t": world.a},
        )
    assert client.get("/auth/me").status_code == 401
    sign_in("planner")  # a new sign-in clears the tenant's expired sessions
    with world.owner.connect() as conn:
        expired = conn.execute(
            text("SELECT count(*) FROM sessions WHERE tenant_id = :t AND expires_at <= now()"),
            {"t": world.a},
        ).scalar_one()
    assert expired == 0


def test_tenant_isolation_through_the_session(world: World, sign_in: SignIn) -> None:
    with world.owner.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO plants (tenant_id, plant_code, name, timezone_iana) "
                "VALUES (:b, 'ONLY-B', 'Only B', 'UTC')"
            ),
            {"b": world.b},
        )
    client = sign_in("coo", "a")
    assert client.get("/plants/ONLY-B/summary").status_code == 404
    assert "ONLY-B" not in {p["plant_code"] for p in client.get("/plants").json()}
    assert sign_in("coo", "b").get("/plants/ONLY-B/summary").status_code == 200


def test_unknown_or_disabled_account_cannot_sign_in(world: World) -> None:
    client = make_client()
    body = {"tenant_id": str(world.a), "email": "nobody@a.example.test"}
    assert client.post("/auth/dev-login", json=body).status_code == 401
    with world.owner.begin() as conn:
        conn.execute(
            text("UPDATE users SET status = 'disabled' WHERE email = :e"), {"e": world.email("coo")}
        )
    body = {"tenant_id": str(world.a), "email": world.email("coo")}
    assert client.post("/auth/dev-login", json=body).status_code == 401
    # Same account in the other tenant does not exist under tenant a's id.
    body = {"tenant_id": str(world.a), "email": world.email("coo", "b")}
    assert client.post("/auth/dev-login", json=body).status_code == 401


def test_invited_account_becomes_active_on_first_sign_in(world: World) -> None:
    with world.owner.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (tenant_id, email, role) "
                "VALUES (:t, 'new@a.example.test', 'planner')"
            ),
            {"t": world.a},
        )
    body = {"tenant_id": str(world.a), "email": "NEW@a.example.test"}
    assert make_client().post("/auth/dev-login", json=body).status_code == 204
    with world.owner.connect() as conn:
        assert (
            conn.execute(
                text("SELECT status FROM users WHERE email = 'new@a.example.test'")
            ).scalar_one()
            == "active"
        )


def test_dev_login_and_header_do_not_exist_outside_dev(world: World) -> None:
    client = make_client(Settings(env="production"))
    body = {"tenant_id": str(world.a), "email": world.email("coo")}
    assert client.post("/auth/dev-login", json=body).status_code == 404
    response = client.get("/auth/me", headers={"X-Tenant-Id": str(world.a)})
    assert response.status_code == 401 and response.json()["detail"] == "sign-in required"


def test_station_session_is_bound_to_the_machine(world: World, sign_in: SignIn) -> None:
    me = sign_in("station").get("/auth/me").json()
    assert me["role"] == "station" and me["subject_type"] == "station"
    assert me["subject_id"] == str(world.station_id)
    assert (me["plant_code"], me["resource_code"]) == ("PLANT-1", "PNT-01")
    assert me["start_page"] == "station"


def test_wrong_pins_lock_the_station_login(world: World) -> None:
    client = make_client()
    body = {"tenant_id": str(world.a), "plant_code": "PLANT-1", "resource_code": "PNT-01"}
    for _ in range(5):
        response = client.post("/auth/station-login", json=body | {"pin": "0000"})
        assert response.status_code == 401
    assert client.post("/auth/station-login", json=body | {"pin": PIN}).status_code == 403
    with world.owner.connect() as conn:
        row = conn.execute(
            text("SELECT status, failed_attempts FROM station_logins WHERE station_login_id = :s"),
            {"s": world.station_id},
        ).one()
        actions = (
            conn.execute(text("SELECT action FROM audit_log WHERE tenant_id = :t"), {"t": world.a})
            .scalars()
            .all()
        )
    assert tuple(row) == ("locked", 5) and "station_login_locked" in actions


def test_station_in_another_tenant_is_not_found(world: World) -> None:
    body = {
        "tenant_id": str(world.b),
        "plant_code": "PLANT-1",
        "resource_code": "PNT-01",
        "pin": PIN,
    }
    assert make_client().post("/auth/station-login", json=body).status_code == 401


class _Jwks:
    def __init__(self, key: Any) -> None:
        self.key = key

    def get_signing_key_from_jwt(self, token: str) -> "_Jwks":
        return self


OIDC = Settings(
    env="production",
    auth_provider="oidc",
    oidc_issuer="https://login.example.test/tenant/v2.0",
    oidc_audience="cip-test-client",
    oidc_jwks_url="https://login.example.test/keys",
)


@pytest.fixture
def signing_key(monkeypatch: pytest.MonkeyPatch) -> rsa.RSAPrivateKey:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(oidc, "_jwks", lambda url: _Jwks(key.public_key()))
    return key


def _token(key: rsa.RSAPrivateKey, **overrides: Any) -> str:
    now = int(time.time())
    claims = {
        "iss": OIDC.oidc_issuer,
        "aud": OIDC.oidc_audience,
        "iat": now,
        "exp": now + 300,
        "preferred_username": "COO@a.example.test",
    } | overrides
    return jwt.encode(claims, key, algorithm="RS256")


def test_oidc_sign_in(world: World, signing_key: rsa.RSAPrivateKey) -> None:
    client = make_client(OIDC, base_url="https://testserver")
    body = {"tenant_id": str(world.a), "id_token": _token(signing_key)}
    response = client.post("/auth/oidc-login", json=body)
    assert response.status_code == 204
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "secure" in response.headers["set-cookie"].lower()
    assert client.get("/auth/me").json()["role"] == "coo"


@pytest.mark.parametrize(
    "overrides",
    [{"aud": "someone-else"}, {"iss": "https://evil.example.test"}, {"exp": 1}],
    ids=["audience", "issuer", "expired"],
)
def test_oidc_rejects_bad_tokens(
    world: World, signing_key: rsa.RSAPrivateKey, overrides: dict[str, Any]
) -> None:
    body = {"tenant_id": str(world.a), "id_token": _token(signing_key, **overrides)}
    response = make_client(OIDC, base_url="https://testserver").post("/auth/oidc-login", json=body)
    assert response.status_code == 401


def test_oidc_rejects_a_token_signed_by_another_key(
    world: World, signing_key: rsa.RSAPrivateKey
) -> None:
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    body = {"tenant_id": str(world.a), "id_token": _token(other)}
    response = make_client(OIDC, base_url="https://testserver").post("/auth/oidc-login", json=body)
    assert response.status_code == 401
