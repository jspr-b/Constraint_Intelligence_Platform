"""Mapping an upload is safe when the preview (API) and the run (worker) map it at once."""

import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from cip_api.imports import ID_RULE, map_import

CLEAN = Path(__file__).resolve().parents[3] / "data/synthetic/plant_a/erp_export/clean/csv"
PLANT = {"plant_code": "PLANT-1", "name": "Plant 1", "timezone_iana": "Europe/Amsterdam"}


def test_two_mappings_of_one_upload_at_once_both_succeed(tmp_path: Path) -> None:
    shutil.copytree(CLEAN, tmp_path / "source")
    map_import(tmp_path, PLANT)
    with ThreadPoolExecutor(2) as pool:
        for report in pool.map(lambda _: map_import(tmp_path, PLANT), range(4)):
            assert report is not None
    assert (tmp_path / "standard" / ID_RULE).exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["source", "standard"]
