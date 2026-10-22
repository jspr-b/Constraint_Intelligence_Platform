"""Constraint detection: several methods, one answer, agreement and plain reasons."""

from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest
import yaml

from constraint_engine.detection import METHODS, Detection, detect_periods
from constraint_engine.facts import measured_facts
from constraint_engine.figure import Confidence
from constraint_engine.formulas.registry import registry
from constraint_engine.io.plant_loader import LoadedPlant, load_plant

DATA = Path(__file__).resolve().parents[3] / "data" / "synthetic"


def _whole(plant: LoadedPlant, gaps: tuple[Confidence, ...] = ()) -> Detection:
    detections = detect_periods(plant, measured_facts(plant), gaps, kinds=("all",))
    assert len(detections) == 1
    return detections[0][1]


@pytest.fixture(scope="module")
def plant_a() -> LoadedPlant:
    return load_plant(DATA / "plant_a")


@pytest.mark.parametrize("name", ["plant_a", "plant_b", "plant_c"])
def test_detection_matches_the_known_answer(name: str) -> None:
    expected = yaml.safe_load((DATA / name / "expected_answers.yaml").read_text())
    found = _whole(load_plant(DATA / name))
    want = expected["constraint"]
    assert (found.resource_code or "none") == want
    assert found.kind == expected["constraint_kind"]
    assert found.confidence is Confidence.HIGH
    assert found.agreement.value == 100.0


def test_every_method_is_a_registered_formula_with_its_evidence(plant_a: LoadedPlant) -> None:
    found = _whole(plant_a)
    assert [m.method for m in found.methods] == list(METHODS)
    for m in found.methods:
        registry.get(m.evidence.formula_id)
        assert m.evidence.period_start_at and m.evidence.inputs
    assert found.reasons[0].code == "methods_agree"
    assert found.reasons[0].values == {"count": 4, "total": 4, "machine": "PNT-01"}


def test_no_internal_constraint_is_said_plainly() -> None:
    found = _whole(load_plant(DATA / "plant_b"))
    assert found.resource_code is None and found.kind == "market"
    assert found.reasons[0].code == "no_machine_binding"
    assert found.reasons[0].values["top"] == "PNT-01"


def test_late_material_makes_it_a_material_constraint() -> None:
    plant = load_plant(DATA / "plant_b")
    late = [
        o.model_copy(update={"material_ready_at": o.released_at + timedelta(days=2)})
        if o.released_at and i % 2 == 0
        else o
        for i, o in enumerate(plant.orders)
    ]
    found = _whole(replace(plant, orders=late))
    assert found.kind == "material" and found.reasons[0].code == "material_late"


def test_a_serious_data_gap_lowers_confidence(plant_a: LoadedPlant) -> None:
    found = _whole(plant_a, (Confidence.HIGH,))
    assert found.resource_code == "PNT-01" and found.confidence is Confidence.MEDIUM
    assert found.reasons[-1].code == "data_gap"


def test_without_scans_starved_blocked_is_less_certain(plant_a: LoadedPlant) -> None:
    from cip_schema.transactional import EventType

    no_scans = replace(
        plant_a,
        events=[e for e in plant_a.events if e.event_type not in (EventType.SCAN, EventType.MOVE)],
    )
    found = _whole(no_scans)
    starved_blocked = next(m for m in found.methods if m.method == "starved_blocked")
    assert starved_blocked.evidence.confidence is not Confidence.HIGH
    assert found.resource_code == "PNT-01"
    assert found.confidence is not Confidence.HIGH


def test_every_week_and_month_gets_a_detection(plant_a: LoadedPlant) -> None:
    detections = detect_periods(plant_a, measured_facts(plant_a))
    kinds = [k for k, _ in detections]
    assert kinds.count("all") == 1 and kinds.count("month") == 4 and kinds.count("week") == 12
    assert all(d.resource_code == "PNT-01" for _, d in detections)
