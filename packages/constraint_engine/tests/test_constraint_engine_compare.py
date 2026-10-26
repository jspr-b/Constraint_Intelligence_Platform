"""What an upload changes (ADR-0010): events added and removed, lists new and gone, warnings."""

from dataclasses import replace
from pathlib import Path

from constraint_engine.io.compare import compare_plants
from constraint_engine.io.plant_loader import LoadedPlant, load_plant

PLANT_A = Path(__file__).resolve().parents[3] / "data" / "synthetic" / "plant_a"


def test_the_same_plant_changes_nothing() -> None:
    a = load_plant(PLANT_A)
    preview = compare_plants(a, a)
    assert preview.events_added == preview.events_removed == 0
    assert preview.lists == [] and preview.warnings == []


def test_second_half_of_the_events_is_counted_as_added() -> None:
    a = load_plant(PLANT_A)
    first = replace(a, events=a.events[: len(a.events) // 2])
    preview = compare_plants(first, a)
    assert preview.events_added == len(a.events) - len(first.events)
    assert preview.events_removed == 0 and preview.warnings == []
    assert preview.period_after[1] and preview.period_before[1]
    assert preview.period_after[1] > preview.period_before[1]


def test_removing_a_step_that_has_events_warns() -> None:
    a = load_plant(PLANT_A)
    fewer = replace(
        a,
        resources=[r for r in a.resources if r.resource_code != "PCK-01"],
        events=[e for e in a.events if e.resource_code != "PCK-01"],
    )
    preview = compare_plants(a, fewer)
    (steps,) = [c for c in preview.lists if c.name == "resources"]
    assert steps.gone == ("PCK-01",) and steps.before == 6 and steps.after == 5
    codes = {w.code: w for w in preview.warnings}
    assert codes["steps_removed_with_events"].items == ("PCK-01",)
    assert codes["events_removed"].count == preview.events_removed > 0


def test_a_shorter_period_warns() -> None:
    a = load_plant(PLANT_A)
    shorter: LoadedPlant = replace(a, events=a.events[100:])
    preview = compare_plants(a, shorter)
    assert "period_shrinks" in {w.code for w in preview.warnings}
