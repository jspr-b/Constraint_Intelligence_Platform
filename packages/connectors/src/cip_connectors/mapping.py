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
    generate: Literal["row_id", "content_id"] | None = None
    """``row_id``: ``<prefix><file>-<line>``. ``content_id``: a hash of the row's other mapped
    fields, so the same event gets the same id in every upload (ADR-0010)."""
    format: str | None = None
    """Date-time format of this field when it differs from the mapping's (mapping wizard)."""
    time_from: str | None = None
    """A second column with the time of day, when date and time are split over two columns;
    ``format`` is then the date's and ``time_format`` the time's."""
    time_format: str | None = None
    scale: str | None = None
    """Multiply the number by this (``60``: hours given, minutes stored)."""
    as_code: bool = False
    """A step or station code: written in capitals, any other character as ``-`` (``Welding
    cell`` -> ``WELDING-CELL``), so a plant's own code or name fits the standard code rule."""
    skip_values: tuple[str, ...] = ()
    """Codes whose rows the client chose to leave out: the line is left out, not rejected."""

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
    reader: Literal["files", "wizard"] = "files"
    """``files``: ``source`` is a file name without extension. ``wizard``: ``source`` is the
    wizard's table id (``file`` or ``file#sheet``), read the way the wizard read it (title
    lines, totals line, each sheet a table)."""
    overrides: dict[str, dict[str, dict[str, str]]] = {}
    """Values the client gave, per target, per key (the target's first column), per field:
    a step's name and kind (mapping wizard)."""


def load_mapping(path: Path | str) -> MappingSet:
    return MappingSet.model_validate(yaml.safe_load(Path(path).read_text()))
