"""The flow found in the data (CI0005 seq 06): each test export, mapped from its confirmed
summary, gives its plant's known routes and arrows, through the case's code table."""

from pathlib import Path
from typing import Any

import pytest
import yaml

from cip_connectors.importer import import_export
from cip_connectors.wizard import recognise_export
from cip_connectors.wizard.plan import build_mapping, plan_from
from constraint_engine.io.plant_loader import load_plant
from constraint_engine.reconstruct.routes import plant_flow

CASES = Path(__file__).resolve().parents[3] / "data" / "synthetic" / "wizard_cases"
NAMES = sorted(p.name for p in CASES.iterdir() if (p / "expected.yaml").exists())
BOOKINGS = {"ridder_hours"}
"""Hour bookings need a duration, so work still running when the export was made is not in
them: plant A's two unfinished visits (SO-24475 at WLD-01, SO-24378 at PNT-01) shorten two
jobs' paths. The scan exports keep them, marked as a missing finish."""
UNFINISHED = 2


@pytest.mark.parametrize("name", NAMES)
def test_the_flow_of_each_export_matches_its_known_answer(name: str, tmp_path: Path) -> None:
    exp: dict[str, Any] = yaml.safe_load((CASES / name / "expected.yaml").read_text())
    found = recognise_export(sorted((CASES / name).iterdir()))
    import_export(CASES / name, build_mapping(plan_from(found)), tmp_path)
    flow = plant_flow(load_plant(tmp_path))
    std = exp["code_tables"].get("resource", {})

    def code(c: str) -> str:  # the plant's own code to the known answer's
        return str(std.get(c, c))

    want = exp["flow"]
    assert flow.jobs == want["jobs"]
    routes = {tuple(code(s) for s in r.steps): r for r in flow.routes}
    arrows = {(code(a.from_step), code(a.to_step)): a for a in flow.arrows}
    if name in BOOKINGS:
        off = sum(
            abs((routes[tuple(r["steps"])].jobs if tuple(r["steps"]) in routes else 0) - r["jobs"])
            for r in want["routes"]
        )
        off += sum(
            abs(
                (arrows[(a["from"], a["to"])].jobs if (a["from"], a["to"]) in arrows else 0)
                - a["jobs"]
            )
            for a in want["arrows"]
        )
        assert off <= 2 * UNFINISHED, off  # each unfinished visit: one route and one arrow
        return
    assert [([code(s) for s in r.steps], r.jobs, r.share.value, r.rework) for r in flow.routes] == [
        (r["steps"], r["jobs"], r["share_pct"], r["rework"]) for r in want["routes"]
    ]
    assert flow.other_routes_jobs == want["other_routes_jobs"]
    got = sorted((code(a.from_step), code(a.to_step), a.jobs, a.share.value) for a in flow.arrows)
    assert got == sorted(
        (a["from"], a["to"], a["jobs"], a["share_of_leaving_pct"]) for a in want["arrows"]
    )
    assert all(a.less_certain for a in flow.arrows if a.rework)  # rework is marked
    assert all(a.share.inputs["jobs"] == a.jobs for a in flow.arrows)  # every share explained
