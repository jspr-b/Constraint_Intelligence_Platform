"""Effective access for a role: ADR-0007 defaults with the COO's changes applied.

Pages default to allowed. Start pages, the COO's access page and IT's users page cannot be
turned off; managing logins (IT) and changing access (COO) cannot be reassigned.
"""

from dataclasses import dataclass

from sqlalchemy import Connection, text

from cip_api.auth.roles import (
    DEFAULT_DECISIONS,
    LOCKED_DECISIONS,
    PAGES,
    START_PAGE,
    Decision,
    Money,
    Plants,
    Role,
)

LOCKED_PAGES = {(r, p) for r, p in START_PAGE.items()} | {(Role.COO, "access"), (Role.IT, "users")}


@dataclass(frozen=True, slots=True)
class Access:
    role: Role
    pages: frozenset[str]
    money: Money
    plants: Plants
    decisions: frozenset[Decision]

    @property
    def start_page(self) -> str:
        return START_PAGE[self.role]


def page_locked(role: Role, page: str) -> bool:
    return (role, page) in LOCKED_PAGES


def decision_locked(decision: Decision) -> bool:
    return decision in LOCKED_DECISIONS


def default_access(role: Role) -> Access:
    return Access(
        role=role,
        pages=frozenset(PAGES),
        money=Money.EUR,
        plants=Plants.ALL,
        decisions=frozenset(d for d, roles in DEFAULT_DECISIONS.items() if role in roles),
    )


def load_access(conn: Connection, role: Role) -> Access:
    """Defaults plus this tenant's overrides (``conn`` is already scoped to the tenant)."""
    base = default_access(role)
    pages = set(base.pages)
    for page, allowed in conn.execute(
        text("SELECT page, allowed FROM access_pages WHERE role = :r"), {"r": role.value}
    ):
        if page in PAGES and not page_locked(role, page):
            (pages.add if allowed else pages.discard)(page)
    decisions = set(base.decisions)
    for name, allowed in conn.execute(
        text("SELECT decision, allowed FROM access_decisions WHERE role = :r"), {"r": role.value}
    ):
        decision = Decision(name)
        if not decision_locked(decision):
            (decisions.add if allowed else decisions.discard)(decision)
    data = conn.execute(
        text("SELECT money, plants FROM access_data WHERE role = :r"), {"r": role.value}
    ).first()
    return Access(
        role=role,
        pages=frozenset(pages),
        money=Money(data.money) if data else base.money,
        plants=Plants(data.plants) if data else base.plants,
        decisions=frozenset(decisions),
    )
