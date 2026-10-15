"""Mapping files: how a source system's tables become the standard layout.

A mapping is organised by *target* field: for every standard field, where it comes from and
how to convert it. Required standard fields the mapping does not cover are reported as
missing, never guessed (ADR-0003).
"""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

ValueType = Literal["str", "int", "decimal", "eur_cents", "datetime", "bool", "list"]


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FieldRule(_M):
    """How one standard field is filled."""

    from_: str | None = Field(default=None, alias="from")
    type: ValueType = "str"
    values: dict[str, str] | None = None
    code_table: str | None = None
    prefix: str = ""
    optional: bool = False
    constant: str | None = None
    generate: Literal["row_id"] | None = None

    @model_validator(mode="after")
    def _one_source(self) -> "FieldRule":
        sources = [self.from_ is not None, self.constant is not None, self.generate is not None]
        if sum(sources) != 1:
            raise ValueError("a field needs exactly one of: from, constant, generate")
        return self


class TableMapping(_M):
    source: str
    """Source table name: ``<source>.csv`` or ``<source>.xlsx`` in the export directory."""
    target: str
    """Standard file name without extension, e.g. ``events``."""
    unique: bool = False
    """Drop duplicate output rows (e.g. stations derived from a machine list)."""
    fields: dict[str, FieldRule]


class MappingSet(_M):
    source_system: str
    timezone: str
    decimal: str = "."
    delimiter: str = ","
    datetime_format: str = "%Y-%m-%dT%H:%M:%S"
    true_values: tuple[str, ...] = ("true", "1", "yes", "ja", "y", "j")
    false_values: tuple[str, ...] = ("false", "0", "no", "nee", "n")
    personal_columns: tuple[str, ...] = ()
    code_tables: dict[str, dict[str, str]] = {}
    tables: tuple[TableMapping, ...]


def load_mapping(path: Path | str) -> MappingSet:
    return MappingSet.model_validate(yaml.safe_load(Path(path).read_text()))
