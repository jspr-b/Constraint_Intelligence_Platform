"""Turn plant D into the export a workshop scan system would send (ADR-0009).

A second export format next to plant A's Dutch ERP export: English column names, commas,
local times (``yyyy-mm-dd hh:mm``), euros with a decimal point, the plant's own step codes, and
an operator column with clearly fake values that the import must drop. No products, routings or
step numbers: one steps list, a shift plan with staffed positions, the team and its plan, the
jobs with their value, and one scan log.

``uv run python -m constraint_engine.synthetic.scan_export <plant dir> <out dir>``
"""

import csv
import json
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ACTION = {
    "start": "START",
    "end": "FINISH",
    "down_start": "STOP",
    "down_end": "RESTART",
    "scan": "ARRIVE",
    "move": "LEAVE",
}
JOB_STATUS = {
    "open": "Open",
    "released": "Released",
    "in_progress": "In progress",
    "shipped": "Shipped",
}
WINDOW = {"shift": "Shift", "break": "Break", "maintenance": "Maintenance", "holiday": "Holiday"}
KIND = {"machine": "Machine", "manual": "Handwork"}
FAKE_OPERATORS = [f"TEST-OPERATOR-{n:02d}" for n in range(1, 9)]
"""Clearly fake values: the import must drop this column, never store it."""

Row = dict[str, Any]


def _rows(path: Path) -> list[Row]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _write(path: Path, columns: list[str], rows: list[Row]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


class ScanExporter:
    def __init__(self, plant_dir: Path) -> None:
        self.src = plant_dir
        tz = json.loads((plant_dir / "plant.json").read_text())["timezone_iana"]
        self.tz = ZoneInfo(tz)
        self.rng = random.Random(2026)
        self.stations = {r["station_code"]: r["name"] for r in _rows(plant_dir / "stations.csv")}

    def local(self, iso: str) -> str:
        if not iso:
            return ""
        moment = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(self.tz)
        return moment.strftime("%Y-%m-%d %H:%M")

    @staticmethod
    def euros(cents: str) -> str:
        return f"{int(cents) / 100:.2f}" if cents else ""

    def write(self, out: Path) -> None:
        out.mkdir(parents=True, exist_ok=True)
        steps = _rows(self.src / "resources.csv")
        _write(
            out / "workstations.csv",
            ["Workstation", "Description", "Area code", "Area", "Type", "Positions"],
            [
                {
                    "Workstation": r["resource_code"],
                    "Description": r["name"],
                    "Area code": r["station_code"],
                    "Area": self.stations[r["station_code"]],
                    "Type": KIND[r["kind"]],
                    "Positions": r["parallel_units"],
                }
                for r in steps
            ],
        )
        _write(
            out / "shift_plan.csv",
            ["Workstation", "Type", "Start", "End", "Staffed"],
            [
                {
                    "Workstation": w["resource_code"],
                    "Type": WINDOW[w["kind"]],
                    "Start": self.local(w["start_at"]),
                    "End": self.local(w["end_at"]),
                    "Staffed": w.get("positions", ""),
                }
                for w in _rows(self.src / "calendar.csv")
            ],
        )
        _write(
            out / "teams.csv",
            ["Team", "Name", "Workstations"],
            [
                {"Team": t["team_code"], "Name": t["name"], "Workstations": t["resource_codes"]}
                for t in _rows(self.src / "teams.csv")
            ],
        )
        _write(
            out / "team_plan.csv",
            ["Team", "Start", "End", "Staffed"],
            [
                {
                    "Team": t["team_code"],
                    "Start": self.local(t["start_at"]),
                    "End": self.local(t["end_at"]),
                    "Staffed": t["positions"],
                }
                for t in _rows(self.src / "team_shifts.csv")
            ],
        )
        _write(
            out / "jobs.csv",
            ["Job", "Qty", "Due", "Status", "Released", "Shipped", "Order value", "Material cost"],
            [
                {
                    "Job": o["order_id"],
                    "Qty": o["quantity_units"],
                    "Due": self.local(o["due_at"]),
                    "Status": JOB_STATUS[o["status"]],
                    "Released": self.local(o["released_at"]),
                    "Shipped": self.local(o["shipped_at"]),
                    "Order value": self.euros(o["order_value_eur_cents"]),
                    "Material cost": self.euros(o["material_cost_eur_cents"]),
                }
                for o in _rows(self.src / "orders.csv")
            ],
        )
        _write(
            out / "scans.csv",
            ["Job", "Workstation", "Area code", "Time", "Action", "Qty", "Reason", "Operator"],
            [
                {
                    "Job": e["order_id"],
                    "Workstation": e["resource_code"],
                    "Area code": e["station_code"],
                    "Time": self.local(e["at"]),
                    "Action": ACTION[e["event_type"]],
                    "Qty": e["quantity_units"],
                    "Reason": e["down_reason_code"],
                    "Operator": self.rng.choice(FAKE_OPERATORS) if e["order_id"] else "",
                }
                for e in _rows(self.src / "events.csv")
            ],
        )


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print(__doc__)
        return 2
    ScanExporter(Path(args[0])).write(Path(args[1]))
    print(f"wrote {args[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
