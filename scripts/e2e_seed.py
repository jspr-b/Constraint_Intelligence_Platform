"""Reset the fixed end-to-end test tenant: one IT account and one empty plant. Synthetic only.

    uv run python scripts/e2e_seed.py

Used by apps/web/playwright.live.config.ts. Deletes only this tenant's rows (cascade).
"""

import uuid

from sqlalchemy import create_engine, text

from cip_api.settings import get_settings

E2E_TENANT = uuid.UUID("0e2e0000-0000-4000-8000-000000000001")


def main() -> None:
    with create_engine(get_settings().db_url(as_owner=True)).begin() as conn:
        conn.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": E2E_TENANT})
        conn.execute(
            text("INSERT INTO tenants (id, name) VALUES (:t, 'E2E Metal (synthetic)')"),
            {"t": E2E_TENANT},
        )
        conn.execute(
            text(
                "INSERT INTO users (tenant_id, email, role, status) "
                "VALUES (:t, 'it@e2e.example.test', 'it', 'active')"
            ),
            {"t": E2E_TENANT},
        )
        conn.execute(
            text(
                "INSERT INTO plants (tenant_id, plant_code, name, timezone_iana) "
                "VALUES (:t, 'PLANT-A', 'Plant A (synthetic)', 'Europe/Amsterdam')"
            ),
            {"t": E2E_TENANT},
        )
    print(E2E_TENANT)


if __name__ == "__main__":
    main()
