"""Tenant context per request (ADR-0004).

Until the login sequence, the tenant comes from the ``X-Tenant-Id`` header, and only when
``CIP_ENV=dev``. Every request runs in a transaction with ``app.tenant_id`` set, so row-level
security applies to every query.
"""

import uuid
from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import Connection, Engine, create_engine, text

from cip_api.settings import Settings, get_settings


def current_tenant(
    settings: Annotated[Settings, Depends(get_settings)],
    x_tenant_id: Annotated[str | None, Header()] = None,
) -> uuid.UUID:
    if settings.env != "dev":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sign-in required")
    if x_tenant_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "X-Tenant-Id header required in dev")
    try:
        return uuid.UUID(x_tenant_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "X-Tenant-Id is not a UUID") from exc


@lru_cache
def _engine(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True)


def tenant_db(
    tenant: Annotated[uuid.UUID, Depends(current_tenant)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Iterator[Connection]:
    """A connection in a transaction with the tenant set (SET LOCAL semantics)."""
    with _engine(settings.db_url()).begin() as conn:
        conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant)})
        yield conn
