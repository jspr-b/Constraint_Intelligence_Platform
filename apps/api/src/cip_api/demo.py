"""Reset the synthetic demo tenant, so a demo always starts from the same place.

    uv run python scripts/demo_reset.py --empty   # tenant + IT account, no plant (live demo)
    uv run python scripts/demo_reset.py --loaded  # plants A, B, C and D imported through the API

With ``--loaded`` plant A goes through the import lifecycle (ADR-0010) like a client would: two
parts, a wrong cut replaced by the right file, a re-export with typing errors and one row fixed
in the app, and a part sent twice by mistake and deleted. Every step has a known answer
(data/synthetic/import_cases), so plant A ends with exactly the answer of its clean export.

Only the demo tenant (fixed id) is deleted and recreated; other tenants are never touched.
``--loaded`` goes through the running API (sign in, add plant, upload, run), exactly like a client
on the Import page, so it needs the stack up (``docker compose up -d --no-build``). Dev only.
"""

import argparse
import json
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import Engine, create_engine, text

from cip_api.settings import get_settings

DEMO_TENANT = uuid.UUID("0de00000-0000-4000-8000-000000000001")
DEMO_TENANT_NAME = "Demo Metal (synthetic)"
DEMO_EMAIL = "it@demo.example"
SYNTHETIC = Path(__file__).resolve().parents[4] / "data" / "synthetic"
DEMO_PLANTS = ("plant_a", "plant_b", "plant_c", "plant_d")


class DemoError(RuntimeError):
    """A step of the demo reset failed; the message says what to do."""


@dataclass(frozen=True)
class DemoPlant:
    plant_code: str
    name: str
    timezone_iana: str
    export_dir: Path


def demo_plant(folder: str, root: Path = SYNTHETIC) -> DemoPlant:
    """The plant's identity from plant.json and its clean ERP-style export."""
    plant = root / folder
    meta = json.loads((plant / "plant.json").read_text())
    return DemoPlant(
        plant_code=meta["plant_code"],
        name=meta["name"],
        timezone_iana=meta["timezone_iana"],
        export_dir=plant / "erp_export" / "clean" / "csv",
    )


def reset_tenant(owner: Engine, tenant: uuid.UUID = DEMO_TENANT) -> None:
    """Delete the demo tenant (cascade) and create it again with one IT account.

    Tests pass their own ``tenant`` so they never touch the live demo.
    """
    with owner.begin() as conn:
        conn.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": tenant})
        conn.execute(
            text("INSERT INTO tenants (id, name) VALUES (:t, :n)"),
            {"t": tenant, "n": DEMO_TENANT_NAME},
        )
        conn.execute(
            text(
                "INSERT INTO users (tenant_id, email, role, status) VALUES (:t, :e, 'it', 'active')"
            ),
            {"t": tenant, "e": DEMO_EMAIL},
        )
        conn.execute(
            text(
                "INSERT INTO audit_log (tenant_id, actor, action, target) "
                "VALUES (:t, 'system:demo_reset', 'user_invited', :e)"
            ),
            {"t": tenant, "e": DEMO_EMAIL},
        )


def _check(response: httpx.Response, step: str) -> httpx.Response:
    if response.is_error:
        raise DemoError(f"{step} failed ({response.status_code}): {response.text[:300]}")
    return response


def _add_plant(client: httpx.Client, plant: DemoPlant) -> None:
    _check(
        client.post(
            "/plants",
            json={
                "plant_code": plant.plant_code,
                "name": plant.name,
                "timezone_iana": plant.timezone_iana,
            },
        ),
        f"adding {plant.plant_code}",
    )


def _files(folder: Path, names: tuple[str, ...] | None = None) -> list[Any]:
    paths = sorted(p for p in folder.glob("*.csv") if names is None or p.name in names)
    if not paths:
        raise DemoError(f"no export files in {folder}")
    return [("files", (p.name, p.read_bytes(), "text/csv")) for p in paths]


def _upload(client: httpx.Client, plant: DemoPlant, folder: Path) -> str:
    upload = _check(
        client.post(f"/plants/{plant.plant_code}/imports", files=_files(folder)),
        f"uploading {plant.plant_code}",
    )
    return str(upload.json()["import_id"])


def _wait(client: httpx.Client, plant: DemoPlant, import_id: str, timeout_s: float) -> None:
    """Until the import is in use and its numbers are calculated (or say why not)."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        state = _check(client.get(f"/imports/{import_id}"), "checking the import").json()
        facts = state.get("facts") or {}
        if state["status"] == "done" and facts.get("status") == "ready":
            return
        if state["status"] == "failed":
            raise DemoError(f"the {plant.plant_code} import failed: {state.get('error')}")
        if facts.get("status") == "failed":
            raise DemoError(
                f"the {plant.plant_code} numbers could not be calculated: {facts.get('error')}"
            )
        time.sleep(1)
    raise DemoError(f"the {plant.plant_code} import did not finish in {timeout_s:.0f} s")


def _run(client: httpx.Client, plant: DemoPlant, import_id: str, timeout_s: float) -> str:
    _check(client.post(f"/imports/{import_id}/run"), f"starting the {plant.plant_code} import")
    _wait(client, plant, import_id, timeout_s)
    return import_id


def _ready(client: httpx.Client, plant: DemoPlant, timeout_s: float) -> None:
    """Until the plant's automatic recalculation after a fix or a delete is done."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        status = _check(client.get("/refresh-status"), "checking the numbers").json()
        mine = next((p for p in status if p["plant_code"] == plant.plant_code), None)
        if mine and mine["status"] == "ready":
            return
        if mine and mine["status"] == "failed":
            raise DemoError(f"the {plant.plant_code} numbers could not be recalculated")
        time.sleep(1)
    raise DemoError(f"the {plant.plant_code} numbers did not update in {timeout_s:.0f} s")


def load_plant(client: httpx.Client, plant: DemoPlant, timeout_s: float = 180) -> str:
    """Add the plant, upload its export and run the import, like a client on the Import page."""
    _add_plant(client, plant)
    return _run(client, plant, _upload(client, plant, plant.export_dir), timeout_s)


FIX = {
    "file": "mes_events.csv",
    "line": 101,
    "column": "Tijdstip",
    "value": "20-07-2026 10:11",
    "reason": "time typed wrong at the bench terminal",
}
"""The first typing error of import_cases/broken, fixed as its expected_answers.yaml says."""


def load_plant_lifecycle(
    client: httpx.Client, plant: DemoPlant, cases: Path, timeout_s: float = 180
) -> str:
    """Plant A as a client builds it up over time (ADR-0010); returns the import in use last.

    1. Part 1 (weeks 1-6 and every list). 2. Part 2 cut wrong (weeks 4-12), then its file
    replaced by the right one (weeks 7-12): a new version. 3. A full re-export with five typing
    errors; one row fixed in the app. 4. Part 2 sent twice by mistake, then deleted.
    """
    _add_plant(client, plant)
    _run(client, plant, _upload(client, plant, cases / "split" / "upload_1"), timeout_s)
    wrong = _run(client, plant, _upload(client, plant, cases / "repeat" / "upload_2"), timeout_s)
    right = _check(
        client.post(f"/imports/{wrong}/files", files=_files(cases / "split" / "upload_2")),
        f"replacing the {plant.plant_code} event file",
    ).json()["import_id"]
    _run(client, plant, str(right), timeout_s)
    export = _run(client, plant, _upload(client, plant, cases / "broken" / "upload_1"), timeout_s)
    _check(client.post(f"/imports/{export}/corrections", json=FIX), "fixing a row")
    _ready(client, plant, timeout_s)
    twice = _run(client, plant, _upload(client, plant, cases / "split" / "upload_2"), timeout_s)
    deadline = time.monotonic() + timeout_s
    while (gone := client.delete(f"/imports/{twice}")).status_code == 409 and (
        gone.json().get("code") == "facts_calculating" and time.monotonic() < deadline
    ):
        time.sleep(1)  # nothing is deleted while the numbers are calculated: wait
    _check(gone, "deleting the upload sent twice")
    _ready(client, plant, timeout_s)
    return export


def load_plants(api_url: str, folders: tuple[str, ...] = DEMO_PLANTS) -> list[str]:
    with httpx.Client(base_url=api_url, timeout=60) as client:
        try:
            _check(
                client.post(
                    "/auth/dev-login", json={"tenant_id": str(DEMO_TENANT), "email": DEMO_EMAIL}
                ),
                "signing in",
            )
        except httpx.ConnectError as exc:
            raise DemoError(
                f"the API at {api_url} is not running: docker compose up -d --no-build"
            ) from exc
        return [
            load_plant_lifecycle(client, demo_plant(f), SYNTHETIC / "import_cases")
            if f == "plant_a"
            else load_plant(client, demo_plant(f))
            for f in folders
        ]


def env_hint(env_file: Path) -> str | None:
    """What to change so the web app signs people into the demo tenant; None if it does."""
    current = ""
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("CIP_DEV_TENANT_ID="):
                current = line.split("=", 1)[1].strip()
    if current == str(DEMO_TENANT):
        return None
    return (
        f"Set CIP_DEV_TENANT_ID={DEMO_TENANT} in {env_file.name} (or rerun with --write-env), "
        "then restart the web app: docker compose up -d --no-build web"
    )


def write_env(env_file: Path) -> None:
    lines = env_file.read_text().splitlines() if env_file.exists() else []
    lines = [ln for ln in lines if not ln.startswith("CIP_DEV_TENANT_ID=")]
    lines.append(f"CIP_DEV_TENANT_ID={DEMO_TENANT}")
    env_file.write_text("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--empty", action="store_true", help="tenant and IT account, no plant")
    mode.add_argument("--loaded", action="store_true", help="plants A, B, C and D imported")
    parser.add_argument("--api-url", default="http://localhost:58000")
    parser.add_argument("--web-url", default="http://localhost:53000")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--write-env", action="store_true", help="point .env at the demo tenant")
    args = parser.parse_args(argv)

    settings = get_settings()
    if settings.env != "dev":
        print("demo_reset only runs with CIP_ENV=dev; it deletes the demo tenant.")
        return 2
    try:
        reset_tenant(create_engine(settings.db_url(as_owner=True)))
        if args.loaded:
            load_plants(args.api_url)
    except DemoError as exc:
        print(f"Demo reset stopped: {exc}")
        return 1
    if args.write_env:
        write_env(args.env_file)
    hint = env_hint(args.env_file)
    plants = "plants A, B, C and D imported" if args.loaded else "no plant yet"
    print(f"Demo ready ({plants}). Sign in at {args.web_url}/login with {DEMO_EMAIL}.")
    if hint:
        print(hint)
    return 0


if __name__ == "__main__":
    sys.exit(main())
