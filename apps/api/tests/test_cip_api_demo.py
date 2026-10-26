"""Demo reset: only the demo tenant changes; --loaded imports A, B, C and D like a client would."""

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml
from sqlalchemy import Engine, text

from cip_api.demo import (
    DEMO_EMAIL,
    DEMO_PLANTS,
    DEMO_TENANT,
    SYNTHETIC,
    demo_plant,
    env_hint,
    load_plant,
    load_plant_lifecycle,
    main,
    reset_tenant,
    write_env,
)
from cip_api.settings import Settings, get_settings
from cip_api_testkit import World, make_client


def _count(owner: Engine, sql: str, tenant: object) -> int:
    with owner.connect() as conn:
        return int(conn.execute(text(sql), {"t": tenant}).scalar_one())


TEST_DEMO = uuid.uuid4()
"""A throwaway tenant: the tests must never touch the live demo tenant."""


@pytest.fixture
def demo(world: World) -> Iterator[World]:
    yield world
    with world.owner.begin() as conn:
        conn.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": TEST_DEMO})


@pytest.mark.db
def test_reset_twice_leaves_one_clean_tenant_and_others_untouched(demo: World) -> None:
    before = _count(demo.owner, "SELECT count(*) FROM users WHERE tenant_id = :t", demo.a)
    reset_tenant(demo.owner, TEST_DEMO)
    reset_tenant(demo.owner, TEST_DEMO)
    users = "SELECT count(*) FROM users WHERE tenant_id = :t"
    assert _count(demo.owner, users, TEST_DEMO) == 1
    assert _count(demo.owner, "SELECT count(*) FROM plants WHERE tenant_id = :t", TEST_DEMO) == 0
    assert _count(demo.owner, users, demo.a) == before
    assert _count(demo.owner, "SELECT count(*) FROM plants WHERE tenant_id = :t", demo.b) == 2


@pytest.mark.db
def test_loaded_imports_plants_a_to_d_through_the_api(demo: World, tmp_path: Path) -> None:
    reset_tenant(demo.owner, TEST_DEMO)
    client = make_client(Settings(env="dev", data_dir=tmp_path, run_jobs_inline=True))
    body = {"tenant_id": str(TEST_DEMO), "email": DEMO_EMAIL}
    assert client.post("/auth/dev-login", json=body).status_code == 204
    for folder in DEMO_PLANTS:
        plant = demo_plant(folder)
        import_id = load_plant(client, plant)
        state = client.get(f"/imports/{import_id}").json()
        assert state["status"] == "done" and state["facts"]["status"] == "ready"
    codes = {p["plant_code"] for p in client.get("/plants").json()}
    assert {"PLANT-A", "PLANT-B", "PLANT-C", "PLANT-D"} <= codes
    reset_tenant(demo.owner, TEST_DEMO)
    assert _count(demo.owner, "SELECT count(*) FROM plants WHERE tenant_id = :t", TEST_DEMO) == 0


@pytest.mark.db
def test_plant_a_goes_through_the_lifecycle_and_keeps_its_known_answer(
    demo: World, tmp_path: Path
) -> None:
    """Two parts, a replaced file, a fixed row and a delete: the answer of the clean export."""
    reset_tenant(demo.owner, TEST_DEMO)
    client = make_client(Settings(env="dev", data_dir=tmp_path, run_jobs_inline=True))
    body = {"tenant_id": str(TEST_DEMO), "email": DEMO_EMAIL}
    assert client.post("/auth/dev-login", json=body).status_code == 204
    load_plant_lifecycle(client, demo_plant("plant_a"), SYNTHETIC / "import_cases")
    history = sorted(client.get("/plants/PLANT-A/imports").json(), key=lambda i: i["created_at"])
    assert [i["status"] for i in history] == ["done", "replaced", "done", "done", "deleted"]
    events = "SELECT count(*) FROM operation_events WHERE tenant_id = :t"
    want = yaml.safe_load((SYNTHETIC / "import_cases" / "expected_answers.yaml").read_text())
    assert _count(demo.owner, events, TEST_DEMO) == want["events_in_plant_a"]
    fixes = client.get("/plants/PLANT-A/corrections").json()
    assert [(c["line"], c["undone"]) for c in fixes] == [(101, False)]
    plant_a = yaml.safe_load((SYNTHETIC / "plant_a" / "expected_answers.yaml").read_text())
    with demo.owner.connect() as conn:
        busy = {
            r.subject_code: float(r.value)
            for r in conn.execute(
                text(
                    "SELECT subject_code, value FROM facts WHERE tenant_id = :t "
                    "AND measure = 'utilisation_pct' AND period_kind = 'all'"
                ),
                {"t": TEST_DEMO},
            )
        }
    for code, value in plant_a["utilisation_pct"].items():
        assert busy[code] == pytest.approx(value, abs=0.1), code
    (whole,) = client.get("/plants/PLANT-A/detection").json()["detections"]
    assert whole["resource_code"] == plant_a["constraint"]
    assert {p["status"] for p in client.get("/refresh-status").json()} == {"ready"}


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


@pytest.mark.db
def test_tests_never_touch_the_live_demo_tenant(demo: World) -> None:
    reset_tenant(demo.owner, TEST_DEMO)
    assert TEST_DEMO != DEMO_TENANT
