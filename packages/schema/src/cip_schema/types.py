"""Shared field types for the standard production-flow model (ADR-0002, ADR-0005)."""

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, StringConstraints


def _require_utc(value: datetime) -> datetime:
    """Reject naive datetimes and normalise aware ones to UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware (ADR-0002); naive values are rejected")
    return value.astimezone(UTC)


UtcDatetime = Annotated[datetime, AfterValidator(_require_utc)]
"""A moment in time, always stored as timezone-aware UTC."""

EurCents = int
"""Money as whole EUR cents. May be negative (e.g. negative throughput)."""

TenantId = UUID

PERSON_WORDS = (
    "operator",
    "operateur",
    "employee",
    "worker",
    "person",
    "personeel",
    "medewerker",
    "werknemer",
    "badge",
    "pasnummer",
    "voornaam",
    "achternaam",
    "firstname",
    "lastname",
    "email",
    "phone",
    "telefoon",
    "mobiel",
    "gebruiker",
    "username",
    "userid",
)
"""Words that point at a person (English and Dutch), ADR-0005. Columns and codes with them
are refused."""


def has_person_word(text: str) -> bool:
    """True when ``text``, ignoring case and punctuation, contains a word for a person."""
    flat = re.sub(r"[^a-z0-9]", "", text.lower())
    return any(word in flat for word in PERSON_WORDS)


def _names_a_place(code: str) -> str:
    if has_person_word(code):
        raise ValueError("a step code names a place where work happens, never a person (ADR-0009)")
    return code


ResourceCode = Annotated[
    str, StringConstraints(pattern=r"^[A-Z][A-Z0-9-]{1,31}$"), AfterValidator(_names_a_place)
]
"""A step's own short code (ADR-0009): ``PNT-01``, ``WELD-BENCH``, ``FIN``. Upper case, digits and
hyphens, 2 to 32 characters; a machine, a handmade bench or a check, never a person."""

StationCode = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9-]{1,31}$")]
"""Station (work area) code such as ``PAINT`` or ``WELD-CELL``."""

Sku = Annotated[str, StringConstraints(min_length=1, max_length=64, strip_whitespace=True)]
OrderId = Annotated[str, StringConstraints(min_length=1, max_length=64, strip_whitespace=True)]
PlantCode = Annotated[str, StringConstraints(pattern=r"^[A-Z0-9][A-Z0-9-]{0,31}$")]


class ResourceState(StrEnum):
    """What a machine is doing at a moment (CLAUDE.md, Core concepts)."""

    RUNNING = "running"
    IDLE = "idle"
    STARVED = "starved"
    BLOCKED = "blocked"
    DOWN = "down"
    SETUP = "setup"
