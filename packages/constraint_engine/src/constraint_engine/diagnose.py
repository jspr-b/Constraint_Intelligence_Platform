"""Offline diagnostic: ``uv run python -m constraint_engine.diagnose <plant dir>``.

Pillar festivals add sections (detection, loss, forecast, recommendations). Until then those
sections answer 'not available yet'.
"""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from constraint_engine.io.plant_loader import LoadedPlant, load_plant
from constraint_engine.quality import quality_report
from constraint_engine.quality.checklist import checklist, parse_requirements
from constraint_engine.quality.render import checklist_lines, markdown, report_lines
from constraint_engine.summary import PlantSummary, summarise

AVAILABLE = ("summary", "quality")
PLANNED = ("detection", "loss", "forecast", "recommendations")


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


def find_input_data(start: Path) -> Path | None:
    """docs/input-data.md in ``start`` or any parent directory."""
    for folder in (start.resolve(), *start.resolve().parents):
        candidate = folder / "docs" / "input-data.md"
        if candidate.exists():
            return candidate
    return None


def _quality(plant: LoadedPlant, args: argparse.Namespace) -> int:
    report = quality_report(plant)
    doc = Path(args.input_data) if args.input_data else find_input_data(Path(args.plant_dir))
    items = checklist(parse_requirements(doc.read_text()), plant) if doc else None
    lines = [*report_lines(report), ""]
    lines += (
        checklist_lines(items)
        if items is not None
        else ["Data checklist: docs/input-data.md not found"]
    )
    print("\n".join(lines))
    if args.md:
        Path(args.md).write_text(markdown(report, items))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="diagnose", description=__doc__)
    parser.add_argument("plant_dir", help="plant directory in the standard layout")
    parser.add_argument("--section", choices=AVAILABLE + PLANNED, default="summary")
    parser.add_argument("--json", action="store_true", help="print Figures with provenance")
    parser.add_argument(
        "--md", help="quality section: also write the report as Markdown to this file"
    )
    parser.add_argument("--input-data", help="path to docs/input-data.md (default: search upwards)")
    args = parser.parse_args(argv)

    if args.section in PLANNED:
        print(f"Section '{args.section}' is not available yet.")
        return 0
    plant = load_plant(args.plant_dir)
    if args.section == "quality":
        return _quality(plant, args)
    summary = summarise(plant)
    print(_json(plant, summary) if args.json else _text(plant, summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
