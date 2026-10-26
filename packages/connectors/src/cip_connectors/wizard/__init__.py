"""Mapping wizard (ADR-0011): recognise a plant's own export and say what it found.

The app suggests and the client confirms. This package only recognises; nothing here imports
data or calls an AI.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from cip_connectors.wizard.columns import ColumnMatch, Target, match_all
from cip_connectors.wizard.profile import profile
from cip_connectors.wizard.roles import _T, MINIMUM, TARGETS, Link, Role, TableRole, classify
from cip_connectors.wizard.tables import ExportTable, read_export

__all__ = ["Recognised", "recognise_export"]


@dataclass
class Recognised:
    tables: list[ExportTable]
    roles: list[TableRole]
    links: list[Link]
    columns: list[ColumnMatch]

    def role_of(self, table_id: str) -> TableRole | None:
        return next((r for r in self.roles if r.table == table_id), None)

    def minimum(self) -> dict[str, list[str]]:
        """For each of the three a diagnostic needs, the tables that give it."""
        return {
            key: [r.table for r in self.roles if r.role in roles and r.sure != "unsure"]
            for key, roles in MINIMUM
        }

    def summary(self) -> dict[str, Any]:
        """The shape of the test exports' ``expected.yaml`` (files section)."""
        files: dict[str, Any] = {}
        for r in self.roles:
            if r.role is None or r.sure == "unsure":
                files[r.table] = {"role": None}
                continue
            targets = sorted(TARGETS[r.role])
            files[r.table] = {"role": targets[0] if len(targets) == 1 else targets}
        columns: dict[str, dict[str, Any]] = {}
        for m in self.columns:
            columns.setdefault(m.table, {})[m.column] = (
                _shown(m.target) if m.sure != "unsure" else None
            )
        return {"files": dict(sorted(files.items())), "columns": columns}


BOOKING = {"bookings.start_at": "booking start", "bookings.duration_min": "booking duration_min"}
"""How the test exports' ``expected.yaml`` names the two booking fields."""


def _shown(target: Target | None) -> Any:
    if isinstance(target, dict):
        return {part: BOOKING.get(field, field) for part, field in target.items()}
    if isinstance(target, str):
        return BOOKING.get(target, target)
    return target


def recognise_export(
    paths: list[Path], answers: Mapping[str, Role | Literal["skip"]] | None = None
) -> Recognised:
    """Recognise an export. ``answers`` are the roles the client gave (``skip`` leaves a table
    out); the columns are matched for the roles as answered."""
    tables = read_export([p for p in paths if p.is_file()])
    roles, links = classify(tables)
    for r in roles:
        given = (answers or {}).get(r.table)
        if given == "skip":
            r.role, r.sure = None, None
        elif given is not None:
            r.role, r.sure = given, "confirmed"
    ts = [_T(t, profile(t)) for t in tables if t.readable]
    return Recognised(tables, roles, links, match_all(ts, roles, links))
