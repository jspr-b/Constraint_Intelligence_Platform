"""Offline diagnostic: ``uv run python -m constraint_engine.diagnose <plant dir>``.

Pillar festivals add sections (detection, loss, forecast, recommendations). Until then those
sections answer 'not available yet'.
"""

import argparse
import json
import sys
from collections.abc import Sequence

from constraint_engine.io.plant_loader import LoadedPlant, load_plant
from constraint_engine.summary import PlantSummary, summarise

AVAILABLE = ("summary",)
PLANNED = ("quality", "detection", "loss", "forecast", "recommendations")


def _text(plant: LoadedPlant, summary: PlantSummary) -> str:
    lines = [f"Plant: {summary.plant_name or 'MISSING (plant.json)'}"]
    for name, fig in summary.counts.items():
        lines.append(f"{name.capitalize()}: {fig.value}")
    if summary.event_period_start_at and summary.event_period_end_at:
        lines.append(
            f"Event period: {summary.event_period_start_at.isoformat()} → "
            f"{summary.event_period_end_at.isoformat()} (UTC)"
        )
    else:
        lines.append("Event period: MISSING (no valid events)")
    lines.append(f"Row errors: {len(plant.row_errors)}")
    for err in plant.row_errors[:20]:
        lines.append(f"  {err.file}:{err.line}  {err.reason}")
    if len(plant.row_errors) > 20:
        lines.append(f"  … {len(plant.row_errors) - 20} more")
    missing = ", ".join(sorted(plant.missing_files)) or "none"
    lines.append(f"Missing files: {missing}")
    return "\n".join(lines)


def _json(plant: LoadedPlant, summary: PlantSummary) -> str:
    return json.dumps(
        {
            "plant_name": summary.plant_name,
            "counts": {k: v.to_dict() for k, v in summary.counts.items()},
            "event_period_start_at": summary.event_period_start_at.isoformat()
            if summary.event_period_start_at
            else None,
            "event_period_end_at": summary.event_period_end_at.isoformat()
            if summary.event_period_end_at
            else None,
            "row_errors": [
                {"file": e.file, "line": e.line, "reason": e.reason} for e in plant.row_errors
            ],
            "missing_files": {k: v.to_dict() for k, v in plant.missing_files.items()},
        },
        indent=2,
        ensure_ascii=False,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="diagnose", description=__doc__)
    parser.add_argument("plant_dir", help="plant directory in the standard layout")
    parser.add_argument("--section", choices=AVAILABLE + PLANNED, default="summary")
    parser.add_argument("--json", action="store_true", help="print Figures with provenance")
    args = parser.parse_args(argv)

    if args.section in PLANNED:
        print(f"Section '{args.section}' is not available yet.")
        return 0
    plant = load_plant(args.plant_dir)
    summary = summarise(plant)
    print(_json(plant, summary) if args.json else _text(plant, summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
