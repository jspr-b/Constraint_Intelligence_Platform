"""The engine on steps and touchpoints (ADR-0009): plant D's known answer from its own truth.

Plant D has handmade steps with positions per shift, a team shared by FINISH and PACK, no
products, no routings, no step numbers, and 4 % forgotten finish scans. Expected values come
from the generator's log (``expected_answers.yaml``, ``generator_log.json``) and the answer fixed
before any code (``known_answer.yaml``); never from engine calculations.
"""

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import yaml

from constraint_engine.detection import Detection, detect_periods
from constraint_engine.facts import Fact, measured_facts
from constraint_engine.figure import Confidence, Missing
from constraint_engine.io.plant_loader import LoadedPlant, load_plant
from constraint_engine.loss import loss_facts
from constraint_engine.reconstruct.durations import pair_operations
from constraint_engine.reconstruct.flow import reconstruct_flow
from constraint_engine.reconstruct.positions import WeightedTimeline, sweep

PLANT_D = Path(__file__).resolve().parents[3] / "data" / "synthetic" / "plant_d"


@pytest.fixture(scope="module")
def plant() -> LoadedPlant:
    return load_plant(PLANT_D)


@pytest.fixture(scope="module")
def facts(plant: LoadedPlant) -> list[Fact]:
    return measured_facts(plant)


@pytest.fixture(scope="module")
def detections(plant: LoadedPlant, facts: list[Fact]) -> list[tuple[str, Detection]]:
    return detect_periods(plant, facts, kinds=("all", "month"))


@pytest.fixture(scope="module")
def loss(
    plant: LoadedPlant, facts: list[Fact], detections: list[tuple[str, Detection]]
) -> list[Fact]:
    return loss_facts(plant, facts, detections)


@pytest.fixture(scope="module")
def expected() -> dict[str, Any]:
    return yaml.safe_load((PLANT_D / "expected_answers.yaml").read_text())  # type: ignore[no-any-return]


@pytest.fixture(scope="module")
def known() -> dict[str, Any]:
    return yaml.safe_load((PLANT_D / "known_answer.yaml").read_text())  # type: ignore[no-any-return]


def _whole(facts: list[Fact], family: str, measure: str) -> dict[str, Fact]:
    return {
        f.subject_code: f
        for f in facts
        if f.family == family and f.measure == measure and f.period_kind == "all"
    }


# --------------------------------------------------------------------------- positions


def test_one_position_counts_like_a_machine_and_three_positions_count_three() -> None:
    shift = (0.0, 100.0)
    one = sweep([(shift, 1)], shift, [(40, 50)], [], [], [(0, 30)], [], [], [], True)
    assert one.weighted["running"].minutes() == 30
    assert one.weighted["break"].minutes() == 10
    assert one.weighted["starved"].minutes() == 60
    three = sweep(
        [(shift, 3)], shift, [(40, 50)], [], [], [(0, 30), (0, 30), (10, 20)], [], [], [], True
    )
    # 3 positions × 100 min; running 30 + 30 + 10; the break takes 3 × 10
    assert three.weighted["shift"].minutes() == 300
    assert three.weighted["running"].minutes() == 70
    assert three.weighted["break"].minutes() == 30
    assert three.weighted["starved"].minutes() == 200
    assert three.saturated == [(10.0, 20.0)]  # all three positions busy


def test_more_jobs_than_positions_never_count_more_than_the_positions() -> None:
    shift = (0.0, 60.0)
    swept = sweep([(shift, 2)], shift, [], [], [], [(0, 60)] * 3, [], [], [], False)
    assert swept.weighted["running"].minutes() == 120
    assert swept.weighted["starved"].minutes() == 0


def test_weighted_minutes_in_a_window() -> None:
    timeline = WeightedTimeline([(0, 10, 2), (20, 30, 3)])
    assert timeline.minutes() == 50
    assert timeline.minutes((5, 25)) == 5 * 2 + 5 * 3


# --------------------------------------------------------------------------- facts


def test_busy_shares_match_the_truth_minus_the_forgotten_scans(
    facts: list[Fact], expected: dict[str, Any]
) -> None:
    """Jobs with a forgotten finish scan are left out (ADR-0009), so a handmade step reads at
    most its forgotten share lower than the truth; machines read exactly the truth."""
    log = json.loads((PLANT_D / "generator_log.json").read_text())
    ends, forgotten = log["end_scans_at_handmade_steps"], log["forgotten_end_scans"]
    busy = _whole(facts, "utilisation", "utilisation_pct")
    for code, truth in expected["utilisation_pct"].items():
        value = float(busy[code].figure.value)  # type: ignore[arg-type]
        steps = log["teams"][code]["steps"] if code in log.get("teams", {}) else [code]
        share = sum(forgotten.get(s, 0) for s in steps) / max(sum(ends.get(s, 1) for s in steps), 1)
        assert truth * (1 - share) - 0.5 <= value <= truth + 0.5, code
    assert busy["FINISH-TEAM"].figure.value == pytest.approx(
        expected["utilisation_pct"]["FINISH-TEAM"], abs=0.5
    )


def test_handmade_steps_and_teams_are_counted_in_position_minutes(facts: list[Fact]) -> None:
    shift = _whole(facts, "state", "shift_min")
    assert shift["FINISH-TEAM"].figure.inputs["counted_in"] == "position-minutes"
    assert shift["WELD-BENCH"].figure.inputs["counted_in"] == "position-minutes"
    assert "counted_in" not in shift["LASER"].figure.inputs
    # WELD-BENCH has 3 positions in both shifts: three times LASER's shift minutes
    assert shift["WELD-BENCH"].figure.value == pytest.approx(
        3 * float(shift["LASER"].figure.value)  # type: ignore[arg-type]
    )


def test_forgotten_scans_are_counted_and_lower_confidence(facts: list[Fact]) -> None:
    gaps = _whole(facts, "scan_gap", "unfinished_start_pct")
    assert set(gaps) >= {"WELD-BENCH", "ASSY-BENCH", "FINISH", "PACK", "FINISH-TEAM"}
    assert "LASER" not in gaps  # machines never forget a scan in plant D
    finish = gaps["FINISH"].figure
    assert 3.0 <= float(finish.value) <= 5.0  # type: ignore[arg-type]
    assert finish.formula_id == "unfinished_start_share_pct_v1"
    assert finish.confidence is Confidence.MEDIUM
    busy = _whole(facts, "utilisation", "utilisation_pct")
    assert busy["FINISH"].figure.confidence is Confidence.MEDIUM
    assert "unfinished_start_pct" in busy["FINISH"].figure.inputs


def test_handmade_performance_without_a_standard_time_is_missing_not_zero(
    facts: list[Fact],
) -> None:
    perf = _whole(facts, "oee", "performance_ratio")
    oee = _whole(facts, "oee", "oee_ratio")
    avail = _whole(facts, "oee", "availability_ratio")
    for code in ("WELD-BENCH", "FINISH"):
        value = perf[code].figure.value
        assert isinstance(value, Missing) and "standard time" in value.reason
        assert isinstance(oee[code].figure.value, Missing)
        assert not isinstance(avail[code].figure.value, Missing)
    assert not isinstance(perf["LASER"].figure.value, Missing)


# --------------------------------------------------------------------------- path


def test_without_step_numbers_the_path_comes_from_touchpoint_times(plant: LoadedPlant) -> None:
    ops = pair_operations(plant)
    flow = reconstruct_flow(plant, ops)
    assert flow.path_from_history
    hops = flow.transitions
    assert (hops["start_min"] >= hops["end_min"]).all()  # every hand-off goes forward in time
    pairs = set(zip(hops["from_resource"], hops["to_resource"], strict=True))
    assert ("LASER", "PRESS") in pairs and ("FINISH", "PACK") in pairs
    assert ("PACK", "FINISH") not in pairs


def test_queue_figures_say_the_path_came_from_history(facts: list[Fact]) -> None:
    queue = _whole(facts, "queue", "queue_median_min")["FINISH"].figure
    assert queue.inputs["path_from"] == "touchpoint times (no step numbers)"
    assert queue.confidence is not Confidence.HIGH


def test_a_job_that_starts_again_without_finishing_is_a_forgotten_scan(
    plant: LoadedPlant,
) -> None:
    """A second visit's finish never closes a first visit whose finish was forgotten."""
    from datetime import timedelta

    from cip_schema.transactional import EventType

    first = next(
        e
        for e in plant.events
        if e.event_type is EventType.START and e.resource_code == "ASSY-BENCH"
    )

    def at(minutes: int, kind: EventType, n: int) -> object:
        return first.model_copy(
            update={
                "event_id": f"T{n}",
                "event_type": kind,
                "at": first.at + timedelta(minutes=minutes),
            }
        )

    events = [at(0, EventType.START, 1), at(60, EventType.START, 2), at(90, EventType.END, 3)]
    ops = pair_operations(replace(plant, events=events))  # type: ignore[arg-type]
    assert ops.jobs.height == 1 and ops.jobs["wall_min"][0] == 30
    assert [u.missing.reason for u in ops.unpaired] == ["start event without an end"]


# --------------------------------------------------------------------------- detection


def test_the_answer_is_the_finishing_team(
    detections: list[tuple[str, Detection]], known: dict[str, Any]
) -> None:
    whole = next(d for kind, d in detections if kind == "all")
    assert whole.kind == known["constraint_kind"]
    assert whole.resource_code == known["constraint"]
    assert list(whole.covers) == known["constraint_covers"]
    votes = sum(1 for m in whole.methods if m.resource_code == known["constraint"])
    assert votes >= known["min_methods_agreeing"]
    assert whole.confidence.label == known["confidence"]
    assert any(r.code == "team_covers" for r in whole.reasons)
    assert not any(m.resource_code in known["not_constraint"] for m in whole.methods)


# --------------------------------------------------------------------------- loss


def test_euros_come_from_job_value_within_tolerance(
    loss: list[Fact], expected: dict[str, Any], known: dict[str, Any]
) -> None:
    tolerance = known["euro_tolerance_pct"] / 100
    rates = expected["throughput_eur_cents_per_constraint_h_by_month"]
    hours = expected["lost_constraint_h_by_month"]
    months = sorted(hours)
    monthly = sorted(
        (
            f
            for f in loss
            if f.period_kind == "month"
            and f.measure == "lost_eur_cents"
            and f.reason_code == "total"
        ),
        key=lambda f: f.figure.period_start_at,  # type: ignore[arg-type, return-value]
    )
    assert len(monthly) == len(months)
    for month, fig in zip(months, monthly, strict=True):
        truth = sum(hours[month].values()) * rates[month]
        assert float(fig.figure.value) == pytest.approx(truth, rel=tolerance), month  # type: ignore[arg-type]
    whole_rate = next(
        f.figure
        for f in loss
        if f.period_kind == "all" and f.measure == "throughput_per_constraint_h_eur_cents"
    )
    assert whole_rate.formula_id == "job_throughput_per_constraint_h_v1"
    assert whole_rate.inputs["from_products_eur_cents"] == 0
    assert float(whole_rate.value) == pytest.approx(  # type: ignore[arg-type]
        expected["throughput_eur_cents_per_constraint_h"]["jobs"], rel=tolerance
    )


def test_without_prices_or_job_values_only_hours_never_a_guessed_euro(
    plant: LoadedPlant, facts: list[Fact]
) -> None:
    bare = replace(
        plant,
        orders=[
            o.model_copy(update={"order_value_eur_cents": None, "material_cost_eur_cents": None})
            for o in plant.orders
        ],
    )
    loss = loss_facts(bare, facts, detect_periods(bare, facts, kinds=("all",)))
    hours = [f for f in loss if f.measure == "lost_h"]
    euros = [f for f in loss if f.measure == "lost_eur_cents"]
    assert hours and all(not isinstance(f.figure.value, Missing) for f in hours)
    assert euros and all(isinstance(f.figure.value, Missing) for f in euros)
    missing = euros[0].figure.value
    assert isinstance(missing, Missing) and "job values" in missing.reason
