"""Quality report on clean plant A and on a copy with known, injected defects."""

import csv
import shutil
from pathlib import Path

import pytest

from constraint_engine.figure import Confidence
from constraint_engine.io.plant_loader import load_plant
from constraint_engine.quality import Gap, quality_report

PLANT_A = Path(__file__).resolve().parents[3] / "data" / "synthetic" / "plant_a"
CLEAN_GAPS = {("no_downtime", "PCK-01"), ("silent_days", "WLD-01"), ("silent_days", "WLD-02")}


def gap_keys(report_gaps: list[Gap]) -> set[tuple[str, str | None]]:
    return {(g.code, g.resource_code) for g in report_gaps}


def test_clean_plant_a() -> None:
    report = quality_report(load_plant(PLANT_A))
    assert gap_keys(report.gaps) == CLEAN_GAPS
    assert all(g.confidence_impact is Confidence.LOW for g in report.gaps)
    assert report.score.value == 100 - 3 * 2
    assert report.score.formula_id == "data_quality_score_v1"
    assert report.rejected_rows == []


@pytest.fixture
def defective(tmp_path: Path) -> Path:
    """plant_a minus 10 PNT-01 ends and all scrap, plus 3 bad rows and one silent ASM-01 day."""
    root = tmp_path / "plant"
    shutil.copytree(PLANT_A, root, ignore=shutil.ignore_patterns("erp_export"))
    with (root / "events.csv").open(newline="") as fh:
        reader = csv.DictReader(fh)
        columns, rows = reader.fieldnames, list(reader)
    assert columns is not None
    pnt_ends = [
        i for i, r in enumerate(rows) if r["resource_code"] == "PNT-01" and r["event_type"] == "end"
    ]
    drop = set(pnt_ends[100:110])
    asm_day = "2026-08-12"
    keep = [
        r
        for i, r in enumerate(rows)
        if i not in drop
        and r["event_type"] != "scrap"
        and not (r["resource_code"] == "ASM-01" and r["at"].startswith(asm_day))
    ]
    with (root / "events.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(keep)
        for n in range(3):
            fh.write(f"BAD{n},start,2026-08-12 10:00:00,PNT-01,,SO-24001,30,5,0,,\n")
    return root


def test_known_defects_give_exact_gaps_and_score(defective: Path) -> None:
    report = quality_report(load_plant(defective))
    expected = CLEAN_GAPS | {
        ("unpaired_start", "PNT-01"),
        ("no_scrap", None),
        ("silent_days", "ASM-01"),
    }
    assert gap_keys(report.gaps) == expected
    unpaired = next(g for g in report.gaps if g.code == "unpaired_start")
    assert unpaired.count == 10
    assert unpaired.confidence_impact is Confidence.MEDIUM and unpaired.fix
    events = next(f for f in report.files if f.file == "events.csv")
    assert events.rejected == 3
    assert [e.line for e in events.examples][:3] == sorted(e.line for e in events.examples)[:3]
    rows = sum(f.rows for f in report.files)
    rejected_penalty = min(2 * 100 * 3 / (rows + 3), 30)
    by_hand = round(100 - rejected_penalty - (2 * 7) - (4 * 2))  # 2 medium, 4 low gaps
    assert report.score.value == by_hand
    assert report.score.inputs["gaps_medium"] == 2 and report.score.inputs["gaps_low"] == 4


def test_missing_events_file_is_a_high_impact_gap(tmp_path: Path) -> None:
    root = tmp_path / "plant"
    shutil.copytree(PLANT_A, root, ignore=shutil.ignore_patterns("erp_export"))
    (root / "events.csv").unlink()
    report = quality_report(load_plant(root))
    missing = [g for g in report.gaps if g.code == "missing_file"]
    assert [(g.description, g.confidence_impact) for g in missing] == [
        ("events.csv is missing", Confidence.HIGH)
    ]
