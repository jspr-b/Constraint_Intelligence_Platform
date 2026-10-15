"""Measured task times on plant A match the generator's configured run times."""

import math
from pathlib import Path

import pytest

from constraint_engine.figure import Confidence, Missing
from constraint_engine.io.plant_loader import load_plant
from constraint_engine.reconstruct.durations import pair_operations, task_times
from constraint_engine.synthetic.config import load_config

DATA = Path(__file__).resolve().parents[3] / "data" / "synthetic"


@pytest.fixture(scope="module")
def plant_a_ops():  # type: ignore[no-untyped-def]
    return pair_operations(load_plant(DATA / "plant_a"))


def configured() -> dict[tuple[str, str, str], tuple[float, float]]:
    """(machine, operation, sku) -> (configured mean run minutes per unit, cv)."""
    cfg = load_config(DATA / "plant_a" / "config.yaml")
    return {
        (s.resource, s.operation, p.sku): (s.run_min_per_unit, s.cv)
        for p in cfg.products
        for s in p.steps
    }


def test_median_task_time_matches_ground_truth(plant_a_ops) -> None:  # type: ignore[no-untyped-def]
    """Per-order run times are lognormal around the configured mean (generator noise).

    The sample median is compared with the lognormal median, mean x exp(-sigma^2 / 2), within
    3.5 standard errors of a median: 1.2533 x sigma / sqrt(n).
    """
    truth = configured()
    times = task_times(plant_a_ops)
    assert {(t.resource_code, t.operation, t.sku) for t in times} == set(truth)
    for t in times:
        mean, cv = truth[(t.resource_code, t.operation, t.sku or "")]
        sigma = math.sqrt(math.log(1 + cv * cv))
        expected = mean * math.exp(-sigma * sigma / 2)
        n = t.median_min_per_unit.inputs["operations_measured"]
        assert isinstance(n, int)
        tolerance = 3.5 * 1.2533 * sigma / math.sqrt(n)
        assert t.median_min_per_unit.value == pytest.approx(expected, rel=tolerance), t
        assert t.median_min_per_unit.formula_id == "task_time_median_v1"
        p90 = t.p90_min_per_unit.value
        assert isinstance(p90, float) and isinstance(t.median_min_per_unit.value, float)
        assert p90 >= t.median_min_per_unit.value


def test_multi_purpose_machine_split_per_operation(plant_a_ops) -> None:  # type: ignore[no-untyped-def]
    ops = {(t.resource_code, t.operation) for t in task_times(plant_a_ops, per_product=False)}
    assert {("WLD-02", "Weld"), ("WLD-02", "Grind"), ("CUT-01", "Cut"), ("CUT-01", "Mark")} <= ops


def test_setups_match_configured_changeover(plant_a_ops) -> None:  # type: ignore[no-untyped-def]
    setups = plant_a_ops.setups
    assert set(setups["resource_code"].unique()) == {"PNT-01"}
    assert setups["work_min"].median() == pytest.approx(25, rel=0.05)


def test_work_time_excludes_breaks_and_nights(plant_a_ops) -> None:  # type: ignore[no-untyped-def]
    jobs = plant_a_ops.jobs
    assert (jobs["work_min"] <= jobs["wall_min"] + 1e-6).all()
    assert (jobs["wall_min"] - jobs["work_min"]).max() > 60  # some jobs ran over a night


def test_only_jobs_running_at_the_end_are_unpaired(plant_a_ops) -> None:  # type: ignore[no-untyped-def]
    reasons = {u.missing.reason for u in plant_a_ops.unpaired}
    assert reasons <= {"still running at the end of the data"}
    assert len(plant_a_ops.unpaired) <= 6
    assert all(u.missing.confidence_impact is Confidence.NONE for u in plant_a_ops.unpaired)


def test_removed_end_becomes_missing(tmp_path: Path) -> None:
    import csv
    import shutil

    root = tmp_path / "p"
    shutil.copytree(DATA / "plant_a", root, ignore=shutil.ignore_patterns("erp_export"))
    rows = list(csv.DictReader((root / "events.csv").open()))
    victim = next(
        i for i, r in enumerate(rows) if r["event_type"] == "end" and r["resource_code"] == "WLD-01"
    )
    with (root / "events.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(r for i, r in enumerate(rows) if i != victim)
    ops = pair_operations(load_plant(root))
    broken = [u for u in ops.unpaired if u.missing.reason == "start event without an end"]
    assert len(broken) == 1 and isinstance(broken[0].missing, Missing)
    assert broken[0].event.resource_code == "WLD-01"
