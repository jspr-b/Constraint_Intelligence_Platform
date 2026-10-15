"""Code tables: translate a source system's codes into the standard model.

Unknown codes are never guessed: ``lookup`` returns ``None`` and the import reports the
code as missing (ADR-0003).
"""

from collections.abc import Iterable
from enum import StrEnum
from typing import Self

from pydantic import Field, TypeAdapter, model_validator

from cip_schema.base import BaseRecord
from cip_schema.transactional import EventType
from cip_schema.types import ResourceCode


class CodeKind(StrEnum):
    RESOURCE = "resource"
    EVENT_TYPE = "event_type"
    DOWN_REASON = "down_reason"
    SCRAP_REASON = "scrap_reason"


_resource = TypeAdapter(ResourceCode)


class CodeEntry(BaseRecord):
    """One mapping, e.g. ERP machine code ``LAS2`` → ``WLD-02``."""

    source_system: str = Field(min_length=1)
    kind: CodeKind
    source_code: str = Field(min_length=1)
    target_code: str = Field(min_length=1)
    description: str | None = None

    @model_validator(mode="after")
    def _target_fits_kind(self) -> Self:
        if self.kind is CodeKind.RESOURCE:
            _resource.validate_python(self.target_code)
        elif self.kind is CodeKind.EVENT_TYPE:
            EventType(self.target_code)
        return self


class CodeTable:
    """Lookup over code entries for one source system."""

    def __init__(self, entries: Iterable[CodeEntry]) -> None:
        self._map: dict[tuple[CodeKind, str], str] = {}
        for entry in entries:
            key = (entry.kind, entry.source_code)
            if key in self._map and self._map[key] != entry.target_code:
                raise ValueError(f"conflicting mapping for {entry.kind} {entry.source_code!r}")
            self._map[key] = entry.target_code

    def lookup(self, kind: CodeKind, source_code: str) -> str | None:
        """Return the standard code, or ``None`` when the code is unknown."""
        return self._map.get((kind, source_code.strip()))
