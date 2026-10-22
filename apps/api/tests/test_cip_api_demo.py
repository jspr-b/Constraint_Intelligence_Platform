"""Demo reset: only the demo tenant changes; --loaded imports A, B and C like a client would."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, text

from cip_api.demo import (
    DEMO_EMAIL,
    DEMO_PLANTS,
    DEMO_TENANT,
    demo_plant,
    env_hint,
    load_plant,
    main,
    reset_tenant,
    write_env,
)
from cip_api.settings import Settings, get_settings
from cip_api_testkit import World, make_client


def _count(owner: Engine, sql: str, tenant: object) -> int:
    with owner.connect() as conn:
        return int(conn.execute(text(sql), {"t": tenant}).scalar_one())


@pytest.fixture
def demo(world: World) -> Iterator[World]:
    yield world
    with world.owner.begin() as conn:
        conn.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": DEMO_TENANT})


@pytest.mark.db
def test_reset_twice_leaves_one_clean_tenant_and_others_untouched(demo: World) -> None:
    before = _count(demo.owner, "SELECT count(*) FROM users WHERE tenant_id = :t", demo.a)
    reset_tenant(demo.owner)
    reset_tenant(demo.owner)
    users = "SELECT count(*) FROM users WHERE tenant_id = :t"
    assert _count(demo.owner, users, DEMO_TENANT) == 1
    assert _count(demo.owner, "SELECT count(*) FROM plants WHERE tenant_id = :t", DEMO_TENANT) == 0
    assert _count(demo.owner, users, demo.a) == before
    assert _count(demo.owner, "SELECT count(*) FROM plants WHERE tenant_id = :t", demo.b) == 2


@pytest.mark.db
def test_loaded_imports_plants_a_b_and_c_through_the_api(demo: World, tmp_path: Path) -> None:
    reset_tenant(demo.owner)
    client = make_client(Settings(env="dev", data_dir=tmp_path, run_jobs_inline=True))
    body = {"tenant_id": str(DEMO_TENANT), "email": DEMO_EMAIL}
    assert client.post("/auth/dev-login", json=body).status_code == 204
    for folder in DEMO_PLANTS:
        plant = demo_plant(folder)
        import_id = load_plant(client, plant)
        assert client.get(f"/imports/{import_id}").json()["status"] == "done"
    codes = {p["plant_code"] for p in client.get("/plants").json()}
    assert {"PLANT-A", "PLANT-B", "PLANT-C"} <= codes
    reset_tenant(demo.owner)
    assert _count(demo.owner, "SELECT count(*) FROM plants WHERE tenant_id = :t", DEMO_TENANT) == 0


def test_env_hint_until_env_points_at_the_demo_tenant(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("CIP_ENV=dev\nCIP_DEV_TENANT_ID=someone-else\n")
    assert env_hint(env) is not None
    write_env(env)
    assert env_hint(env) is None
    assert env.read_text().count("CIP_DEV_TENANT_ID=") == 1
    assert "CIP_ENV=dev" in env.read_text()


def test_refuses_outside_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CIP_ENV", "production")
    get_settings.cache_clear()
    try:
        assert main(["--empty"]) == 2
    finally:
        get_settings.cache_clear()
