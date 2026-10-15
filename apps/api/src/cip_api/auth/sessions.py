"""Sessions: an opaque token in an httpOnly cookie; the database keeps only its SHA-256.

Tenant and role always come from the session, never from the request.
"""

import hashlib
import secrets
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache

from fastapi import Response
from sqlalchemy import Connection, Engine, create_engine, text

from cip_api.auth.roles import Role
from cip_api.settings import Settings

COOKIE = "cip_session"


@dataclass(frozen=True, slots=True)
class Principal:
    """Who is signed in. A station principal is a machine, never a person (ADR-0005)."""

    tenant_id: uuid.UUID
    subject_type: str
    """``user``, ``station`` or ``dev`` (dev header, dev only)."""
    subject_id: str
    role: Role
    plant_code: str | None = None
    resource_code: str | None = None

    @property
    def actor(self) -> str:
        return f"{self.subject_type}:{self.subject_id}"


@lru_cache
def app_engine(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True)


@contextmanager
def tenant_conn(settings: Settings, tenant: uuid.UUID) -> Iterator[Connection]:
    """A transaction with ``app.tenant_id`` set, so row-level security applies."""
    with app_engine(settings.db_url()).begin() as conn:
        conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant)})
        yield conn


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def audit(
    conn: Connection, tenant: uuid.UUID, actor: str, action: str, target: str, detail: str = ""
) -> None:
    conn.execute(
        text(
            "INSERT INTO audit_log (tenant_id, actor, action, target, detail) "
            "VALUES (:t, :actor, :action, :target, :detail)"
        ),
        {"t": tenant, "actor": actor, "action": action, "target": target, "detail": detail},
    )


def start_session(conn: Connection, settings: Settings, who: Principal, response: Response) -> None:
    """Store a new session for ``who`` (inside its tenant transaction) and set the cookie."""
    token = secrets.token_urlsafe(32)
    # Housekeeping: each sign-in clears this tenant's expired sessions.
    conn.execute(text("DELETE FROM sessions WHERE expires_at <= now()"))
    conn.execute(
        text(
            "INSERT INTO sessions (tenant_id, token_hash, subject_type, subject_id, role, "
            "plant_code, resource_code, expires_at) VALUES (:t, :h, :st, :sid, :role, :plant, "
            ":res, :exp)"
        ),
        {
            "t": who.tenant_id,
            "h": token_hash(token),
            "st": who.subject_type,
            "sid": who.subject_id,
            "role": who.role.value,
            "plant": who.plant_code,
            "res": who.resource_code,
            "exp": datetime.now(UTC) + timedelta(hours=settings.session_hours),
        },
    )
    response.set_cookie(
        COOKIE,
        token,
        max_age=settings.session_hours * 3600,
        httponly=True,
        secure=settings.env != "dev",
        samesite="lax",
        path="/",
    )


def find_session(settings: Settings, token: str) -> Principal | None:
    """The live session for a token, via the one narrow cross-tenant lookup (migration 0003)."""
    with app_engine(settings.db_url()).connect() as conn:
        row = conn.execute(
            text("SELECT * FROM session_lookup(:h)"), {"h": token_hash(token)}
        ).first()
    if row is None:
        return None
    return Principal(
        tenant_id=row.tenant_id,
        subject_type=row.subject_type,
        subject_id=row.subject_id,
        role=Role(row.role),
        plant_code=row.plant_code,
        resource_code=row.resource_code,
    )


def end_sessions(conn: Connection, subject_type: str, subject_id: str) -> None:
    """Sign a subject out everywhere (used when IT disables an account)."""
    conn.execute(
        text("DELETE FROM sessions WHERE subject_type = :st AND subject_id = :sid"),
        {"st": subject_type, "sid": subject_id},
    )
