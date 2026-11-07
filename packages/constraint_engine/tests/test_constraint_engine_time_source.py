"""Times from hour bookings (ADR-0011 §5, CI0005 seq 05): the answer is capped and says why, and
the loss causes bookings cannot tell (setups, stops, starved, blocked) are not available."""

from dataclasses import replace
from pathlib import Path

import pytest

from cip_schema.transactional import TimeSource
from constraint_engine.detection import Detection, detect_periods
from constraint_engine.facts import measured_facts
from constraint_engine.figure import Confidence, Missing
from constraint_engine.io.plant_loader import LoadedPlant, load_plant
from constraint_engine.loss import loss_facts
from constraint_engine.time_source import time_sources

DATA = Path(__file__).resolve().parents[3] / "data" / "synthetic"


@pytest.fixture(scope="module")
def plant_a() -> LoadedPlant:
    return load_plant(DATA / "plant_a")


def _as(plant: LoadedPlant, source: TimeSource) -> LoadedPlant:
    return replace(
        plant, events=[e.model_copy(update={"time_source": source}) for e in plant.events]
    )


def _answer(plant: LoadedPlant) -> Detection:
    ((_, found),) = detect_periods(plant, measured_facts(plant), (), kinds=("all",))
    return found


def test_scans_only_say_nothing(plant_a: LoadedPlant) -> None:
    assert time_sources(plant_a) is None
    found = _answer(plant_a)
    assert found.confidence is Confidence.HIGH
    assert not [r for r in found.reasons if r.code.startswith("times_")]


def test_booked_times_cap_the_answer_at_medium_and_say_why(plant_a: LoadedPlant) -> None:
    found = _answer(_as(plant_a, TimeSource.BOOKING))
    assert found.resource_code == "PNT-01"
    assert found.confidence is Confidence.MEDIUM
    (reason,) = [r for r in found.reasons if r.code == "times_from_bookings"]
    assert reason.values == {"share_pct": 100.0}


def test_estimated_times_cap_the_answer_at_low(plant_a: LoadedPlant) -> None:
    found = _answer(_as(plant_a, TimeSource.ESTIMATED))
    assert found.confidence is Confidence.LOW
    assert [r.code for r in found.reasons if r.code.startswith("times_")] == ["times_estimated"]


def test_loss_causes_bookings_cannot_tell_are_not_available(plant_a: LoadedPlant) -> None:
    plant = _as(plant_a, TimeSource.BOOKING)
    facts = measured_facts(plant)
    loss = loss_facts(plant, facts, detect_periods(plant, facts, (), kinds=("all",)))
    hours = {f.reason_code: f.figure.value for f in loss if f.measure == "lost_h"}
    for cause in ("breakdowns", "setup", "starved", "blocked", "total"):
        value = hours[cause]
        assert isinstance(value, Missing), cause
        assert "hour bookings" in value.reason
    assert not isinstance(hours["breaks"], Missing)  # from the shift sheet, still known


def test_a_step_without_data_does_not_hide_the_answer(plant_a: LoadedPlant) -> None:
    """A step added on Plant setup and never measured is not measured; the others still count."""
    new = plant_a.resources[0].model_copy(update={"resource_code": "NEW-01", "name": "New bench"})
    plant = _as(replace(plant_a, resources=[*plant_a.resources, new]), TimeSource.BOOKING)
    found = _answer(plant)
    assert (found.resource_code, found.kind) == ("PNT-01", "internal")
