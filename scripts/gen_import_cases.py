"""Generate the import-lifecycle test cases (ADR-0010) from plant A's clean ERP export.

    uv run python scripts/gen_import_cases.py           # write
    uv run python scripts/gen_import_cases.py --check   # fail when a file is stale

Every case is cut from data/synthetic/plant_a/erp_export/clean/csv, so its answer is plant A's
known answer (or the first upload's own answer); nothing here is calculated by the engine.
Counts written to expected_answers.yaml are row counts of the files, made here.
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "synthetic" / "plant_a" / "erp_export" / "clean" / "csv"
OUT = ROOT / "data" / "synthetic" / "import_cases"
EVENTS = "mes_events.csv"
TIME_COLUMN = "Tijdstip"
SPLIT_AT = datetime(2026, 8, 31)  # start of week 7 of plant A's 12 weeks (plant local time)
REPEAT_FROM = datetime(2026, 8, 10)  # weeks 4-12: overlaps the first upload by three weeks
BROKEN_LINES = (101, 1501, 3001, 4501, 6001)  # file lines (header is line 1)
BROKEN_TIME = "not a time"


def _read(name: str) -> tuple[str, list[str]]:
    lines = (CLEAN / name).read_text(encoding="utf-8").splitlines()
    return lines[0], lines[1:]


def _at(row: str, header: str) -> datetime:
    value = row.split(";")[header.split(";").index(TIME_COLUMN)]
    return datetime.strptime(value, "%d-%m-%Y %H:%M")


def _csv(header: str, rows: list[str]) -> str:
    return "\n".join([header, *rows]) + "\n"


def build() -> dict[Path, str]:
    """Every file of the cases, by path. Pure: same input, same output."""
    files: dict[Path, str] = {}
    lists = sorted(p.name for p in CLEAN.iterdir() if p.name != EVENTS)
    header, events = _read(EVENTS)
    first = [r for r in events if _at(r, header) < SPLIT_AT]
    second = [r for r in events if _at(r, header) >= SPLIT_AT]
    repeat = [r for r in events if _at(r, header) >= REPEAT_FROM]

    def upload(folder: str, rows: list[str], with_lists: bool) -> None:
        if with_lists:
            for name in lists:
                files[OUT / folder / name] = (CLEAN / name).read_text(encoding="utf-8")
        files[OUT / folder / EVENTS] = _csv(header, rows)

    upload("split/upload_1", first, with_lists=True)
    upload("split/upload_2", second, with_lists=False)
    upload("repeat/upload_2", repeat, with_lists=False)

    broken = list(events)
    column = header.split(";").index(TIME_COLUMN)
    fixes = []
    for line in BROKEN_LINES:
        cells = broken[line - 2].split(";")
        fixes.append({"file": EVENTS, "line": line, "column": TIME_COLUMN, "value": cells[column]})
        cells[column] = BROKEN_TIME
        broken[line - 2] = ";".join(cells)
    upload("broken/upload_1", broken, with_lists=True)

    answers = {
        "source": "data/synthetic/plant_a/erp_export/clean/csv",
        "rule": "ADR-0010. Written before the code; never edited to fit it.",
        "plant_answer": "data/synthetic/plant_a/expected_answers.yaml",
        "events_in_plant_a": len(events),
        "cases": {
            "split": {
                "uploads": ["split/upload_1", "split/upload_2"],
                "note": "Both event files are named mes_events.csv and hold different weeks.",
                "events_per_upload": [len(first), len(second)],
                "events_after": len(events),
                "events_already_there": [0, 0],
                "answer": "plant_answer",
                "after_deleting_upload_2": {
                    "events_after": len(first),
                    "answer": "same as split/upload_1 imported alone",
                },
            },
            "repeat": {
                "uploads": ["split/upload_1", "split/upload_2", "repeat/upload_2"],
                "note": "Weeks 4-12 sent again, cut differently: other line numbers.",
                "events_per_upload": [len(first), len(second), len(repeat)],
                "events_after": len(events),
                "events_already_there": [0, 0, len(repeat)],
                "answer": "plant_answer",
            },
            "whole_twice": {
                "uploads": ["plant_a clean", "plant_a clean"],
                "events_after": len(events),
                "events_already_there": [0, len(events)],
                "answer": "plant_answer",
            },
            "broken_rows_fixed_in_app": {
                "uploads": ["broken/upload_1"],
                "rejected_rows": len(BROKEN_LINES),
                "fixes": fixes,
                "events_after_fixes": len(events),
                "answer_after_fixes": "same as plant_a clean imported once",
            },
        },
    }
    files[OUT / "expected_answers.yaml"] = yaml.safe_dump(answers, sort_keys=False)
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    stale = []
    for path, content in build().items():
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                stale.append(path.relative_to(ROOT))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    for path in stale:
        print(f"stale: {path}", file=sys.stderr)
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
