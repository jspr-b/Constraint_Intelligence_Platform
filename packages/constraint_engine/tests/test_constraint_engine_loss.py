"""Bottleneck loss: lost hours per cause, throughput per bottleneck hour, lost euros."""

from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from constraint_engine.detection import detect_periods
from constraint_engine.facts import Fact, measured_facts
from constraint_engine.figure import Missing
from constraint_engine.formulas.registry import registry
from constraint_engine.io.plant_loader import LoadedPlant, load_plant
from constraint_engine.loss import ALL_CAUSES, loss_facts

DATA = Path(__file__).resolve().parents[3] / "data" / "synthetic"


def _loss(plant: LoadedPlant, kinds: tuple[str, ...] = ("all", "month", "week")) -> list[Fact]:
    facts = measured_facts(plant)
    return loss_facts(plant, facts, detect_periods(plant, facts, kinds=kinds))


@pytest.fixture(scope="module")
def plant_a() -> LoadedPlant:
    return load_plant(DATA / "plant_a")


@pytest.fixture(scope="module")
def loss_a(plant_a: LoadedPlant) -> list[Fact]:
    return _loss(plant_a)


@pytest.fixture(scope="module")
def expected_a() -> dict:  # type: ignore[type-arg]
    return yaml.safe_load((DATA / "plant_a" / "expected_answers.yaml").read_text())  # type: ignore[no-any-return]


def test_lost_hours_per_cause_match_the_generator_log(
    loss_a: list[Fact],
    expected_a: dict,  # type: ignore[type-arg]
) -> None:
    months = sorted({f.figure.period_start_at for f in loss_a if f.period_kind == "month"} - {None})  # type: ignore[type-var]
    want = expected_a["lost_constraint_h_by_month"]
    assert len(months) == len(want)
    for start, key in zip(months, sorted(want), strict=True):
        got = {
            f.reason_code: f.figure.value
            for f in loss_a
            if f.period_kind == "month"
            and f.measure == "lost_h"
            and f.figure.period_start_at == start
        }
        for cause in ALL_CAUSES:
            assert got[cause] == pytest.approx(want[key][f"{cause}_h"], abs=0.01), (key, cause)
        assert got["total"] == pytest.approx(sum(want[key].values()), abs=0.05)


def test_throughput_per_bottleneck_hour_matches_the_known_answer(
    loss_a: list[Fact],
    expected_a: dict,  # type: ignore[type-arg]
) -> None:
    rates = {
        f.reason_code: f.figure
        for f in loss_a
        if f.family == "throughput" and f.period_kind == "all"
    }
    for sku, want in expected_a["throughput_eur_cents_per_constraint_h"].items():
        if want is None:
            assert sku not in rates  # never runs on the bottleneck
        else:
            # measured task times vary around the generator's run time
            assert rates[sku].value == pytest.approx(want, rel=0.05), sku
    mix = rates[None]
    assert mix.unit == "eur_cents_per_h" and mix.formula_id == "throughput_per_constraint_h_v1"
    assert (
        min(want for want in expected_a["throughput_eur_cents_per_constraint_h"].values() if want)
        * 0.95
        <= mix.value
    )


def test_lost_euros_are_hours_times_the_rate(loss_a: list[Fact]) -> None:
    whole = [f for f in loss_a if f.period_kind == "all" and f.family == "loss"]
    rate = next(
        f.figure
        for f in loss_a
        if f.family == "throughput" and f.period_kind == "all" and f.reason_code is None
    )
    hours = {f.reason_code: f.figure for f in whole if f.measure == "lost_h"}
    euros = {f.reason_code: f.figure for f in whole if f.measure == "lost_eur_cents"}
    assert set(hours) == set(euros) == {*ALL_CAUSES, "total"}
    for cause, fig in euros.items():
        assert isinstance(fig.value, int)
        assert fig.value == round(float(hours[cause].value) * float(rate.value))  # type: ignore[arg-type]
        assert fig.inputs["lost_h"] is hours[cause]
        registry.get(fig.formula_id)


def test_without_prices_hours_stay_and_euros_say_what_is_missing(plant_a: LoadedPlant) -> None:
    loss = _loss(replace(plant_a, products=[]), kinds=("all",))
    hours = [f for f in loss if f.measure == "lost_h"]
    euros = [f for f in loss if f.measure == "lost_eur_cents"]
    assert hours and all(not isinstance(f.figure.value, Missing) for f in hours)
    assert euros and all(isinstance(f.figure.value, Missing) for f in euros)
    missing = euros[0].figure.value
    assert isinstance(missing, Missing) and "throughput_eur_cents" in missing.what
    assert "products" in missing.reason


def test_a_plant_without_a_bottleneck_has_no_loss() -> None:
    assert _loss(load_plant(DATA / "plant_b")) == []


def test_scrap_before_the_bottleneck_costs_no_bottleneck_time(plant_a: LoadedPlant) -> None:
    from cip_schema.transactional import EventType

    early = [
        e.model_copy(update={"operation_seq": 1}) if e.event_type is EventType.SCRAP else e
        for e in plant_a.events
    ]
    loss = _loss(replace(plant_a, events=early), kinds=("all",))
    scrap = next(f for f in loss if f.measure == "lost_h" and f.reason_code == "scrap")
    assert scrap.figure.value == 0


def test_scrap_without_step_numbers_is_placed_by_time(plant_a: LoadedPlant) -> None:
    """ADR-0009: a scrap with no step number counts when it happened after the bottleneck."""
    from cip_schema.transactional import EventType

    def scrap_h(plant: LoadedPlant) -> object:
        loss = _loss(plant, kinds=("all",))
        return next(
            f for f in loss if f.measure == "lost_h" and f.reason_code == "scrap"
        ).figure.value

    unnumbered = [
        e.model_copy(update={"operation_seq": None}) if e.event_type is EventType.SCRAP else e
        for e in plant_a.events
    ]
    assert scrap_h(replace(plant_a, events=unnumbered)) == scrap_h(plant_a) != 0


def test_a_plant_without_step_numbers_gets_its_loss_figures() -> None:
    assert _loss(load_plant(DATA / "plant_d"), kinds=("all",))


def test_a_stored_figure_reads_back_the_same(loss_a: list[Fact]) -> None:
    from constraint_engine.figure import Figure

    fig = next(f.figure for f in loss_a if f.measure == "lost_eur_cents")
    assert Figure.from_dict(fig.to_dict()).to_dict() == fig.to_dict()
