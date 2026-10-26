"""Mapping wizard (ADR-0011): recognise a plant's own export and say what it found.

The app suggests and the client confirms. This package only recognises; nothing here imports
data or calls an AI.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cip_connectors.wizard.roles import MINIMUM, TARGETS, Link, TableRole, classify
from cip_connectors.wizard.tables import ExportTable, read_export

__all__ = ["Recognised", "recognise_export"]


@dataclass
class Recognised:
    tables: list[ExportTable]
    roles: list[TableRole]
    links: list[Link]

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
        return {"files": dict(sorted(files.items()))}


def recognise_export(paths: list[Path]) -> Recognised:
    tables = read_export([p for p in paths if p.is_file()])
    roles, links = classify(tables)
    return Recognised(tables, roles, links)
