"""Shared field types for the standard production-flow model (ADR-0002, ADR-0005)."""

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

ResourceCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{2,4}-\d{2}$")]
"""Short machine code such as ``PNT-01`` or ``WLD-02``."""

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
