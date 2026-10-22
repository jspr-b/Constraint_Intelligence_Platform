"""Reconstructed machine states match the generator's own truth log."""

import json
from pathlib import Path

import pytest

from constraint_engine.io.plant_loader import load_plant
from constraint_engine.reconstruct.states import STATES, UNKNOWN, machine_states, period_windows

DATA = Path(__file__).resolve().parents[3] / "data" / "synthetic"
TRUTH_KEY = {
    "break": "break_min",
    "maintenance": "maintenance_min",
    "down": "down_min",
    "running": "running_min",
    "setup": "setup_min",
    "blocked": "blocked_min",
    "starved": "starved_min",
}


@pytest.fixture(scope="module")
def states_a():  # type: ignore[no-untyped-def]
    return machine_states(load_plant(DATA / "plant_a"))


@pytest.mark.parametrize("state", STATES)
def test_states_match_generator_truth(states_a, state: str) -> None:  # type: ignore[no-untyped-def]
    truth = json.loads((DATA / "plant_a" / "generator_log.json").read_text())["machines"]
    for code, ms in states_a.items():
        got = ms.minutes()[state]
        want = truth[code]["total"][TRUTH_KEY[state]]
        # events are stored to the second; allow 1 minute per 1000 plus 2 minutes
        assert got == pytest.approx(want, abs=2 + want / 1000), (code, state)


def test_every_shift_minute_is_one_state(states_a) -> None:  # type: ignore[no-untyped-def]
    for ms in states_a.values():
        m = ms.minutes()
        assert sum(m[s] for s in (*STATES, UNKNOWN)) == pytest.approx(m["shift"], abs=0.5)


def test_paint_line_is_busy_and_welders_are_blocked(states_a) -> None:  # type: ignore[no-untyped-def]
    pnt = states_a["PNT-01"].minutes()
    wld = states_a["WLD-02"].minutes()
    assert (pnt["running"] + pnt["setup"]) / (pnt["running"] + pnt["setup"] + pnt["starved"]) > 0.95
    assert wld["blocked"] > 0


def test_monthly_windows_cover_the_data(states_a) -> None:  # type: ignore[no-untyped-def]
    from datetime import UTC, datetime

    months = period_windows(
        datetime(2026, 7, 20, tzinfo=UTC),
        datetime(2026, 10, 12, tzinfo=UTC),
        "Europe/Amsterdam",
        "M",
    )
    assert list(months) == ["2026-07", "2026-08", "2026-09", "2026-10"]
    pnt = states_a["PNT-01"]
    per_month = sum(pnt.minutes(w)["break"] for w in months.values())
    assert per_month == pytest.approx(pnt.minutes()["break"])


def test_without_scans_blocked_is_missing(tmp_path: Path) -> None:
    import csv
    import shutil

    root = tmp_path / "p"
    shutil.copytree(DATA / "plant_a", root, ignore=shutil.ignore_patterns("erp_export"))
    rows = [
        r
        for r in csv.DictReader((root / "events.csv").open())
        if r["event_type"] not in ("scan", "move")
    ]
    with (root / "events.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    states = machine_states(load_plant(root))
    assert states["WLD-02"].blocked_missing is not None
    assert states["WLD-02"].minutes()["blocked"] == 0
