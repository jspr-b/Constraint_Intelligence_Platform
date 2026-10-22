"""Facts from the ERP-style export of plant A: same answers, and defects lower confidence only.

The engine's own known-answer tests use the standard layout; these run the connector first.
"""

import json
from pathlib import Path

import pytest
import yaml

from cip_connectors.importer import import_export
from cip_connectors.mapping import load_mapping
from constraint_engine.facts import Fact, measured_facts
from constraint_engine.figure import Confidence
from constraint_engine.io.plant_loader import load_plant

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data" / "synthetic"
MAPPING = ROOT / "packages" / "connectors" / "mappings" / "generic" / "mapping.yaml"


def _utilisation(facts: list[Fact]) -> dict[str, Fact]:
    return {
        f.subject_code: f
        for f in facts
        if f.measure == "utilisation_pct" and f.period_kind == "all"
    }


def _expected(plant: str) -> dict[str, float]:
    answers = yaml.safe_load((DATA / plant / "expected_answers.yaml").read_text())
    return dict(answers["utilisation_pct"])


def _from_export(variant: str, tmp_path: Path) -> list[Fact]:
    out = tmp_path / variant
    plant = json.loads((DATA / "plant_a" / "plant.json").read_text())
    source = DATA / "plant_a" / "erp_export" / variant / "csv"
    import_export(source, load_mapping(MAPPING), out, plant=plant)
    return measured_facts(load_plant(out))


def test_the_erp_export_gives_the_same_answers(tmp_path: Path) -> None:
    got = _utilisation(_from_export("clean", tmp_path))
    for code, want in _expected("plant_a").items():
        assert got[code].figure.value == pytest.approx(want, abs=0.1), code


def test_defects_lower_confidence_instead_of_changing_answers(tmp_path: Path) -> None:
    facts = _from_export("defects", tmp_path)
    got = _utilisation(facts)
    for code, want in _expected("plant_a").items():
        assert got[code].figure.value == pytest.approx(want, abs=1.0), code
        assert got[code].figure.confidence is Confidence.MEDIUM, code
    unknown = [f for f in facts if f.measure == "unknown_min" and f.period_kind == "all"]
    assert all(isinstance(f.figure.value, float) and f.figure.value > 0 for f in unknown)
    busiest = max(got.values(), key=lambda f: float(f.figure.value))  # type: ignore[arg-type]
    assert busiest.subject_code == "PNT-01"
