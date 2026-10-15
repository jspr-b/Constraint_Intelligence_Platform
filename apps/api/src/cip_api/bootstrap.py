"""Create a tenant and its first IT account, so IT can invite everyone else.

    uv run python -m cip_api.bootstrap --tenant "Demo Metal BV" --it-email it@demo.example

Runs as the database owner. Use synthetic names only in dev; never real customer data.
"""

import argparse
import uuid

from sqlalchemy import create_engine, text

from cip_api.settings import get_settings


def bootstrap(tenant_name: str, it_email: str) -> uuid.UUID:
    tenant = uuid.uuid4()
    with create_engine(get_settings().db_url(as_owner=True)).begin() as conn:
        conn.execute(
            text("INSERT INTO tenants (id, name) VALUES (:t, :n)"), {"t": tenant, "n": tenant_name}
        )
        conn.execute(
            text("INSERT INTO users (tenant_id, email, role) VALUES (:t, :e, 'it')"),
            {"t": tenant, "e": it_email.lower()},
        )
        conn.execute(
            text(
                "INSERT INTO audit_log (tenant_id, actor, action, target) "
                "VALUES (:t, 'system:bootstrap', 'user_invited', :e)"
            ),
            {"t": tenant, "e": it_email.lower()},
        )
    return tenant


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--it-email", required=True)
    args = parser.parse_args()
    print(bootstrap(args.tenant, args.it_email))


if __name__ == "__main__":
    main()
