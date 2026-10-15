"""Shared test helpers: a tiny plant in the standard layout."""

import json
from collections.abc import Callable
from pathlib import Path

import pytest

FILES = {
    "stations.csv": "station_code,name\nPAINT,Paint\nWELD-CELL,Welding cell\n",
    "resources.csv": (
        "resource_code,name,station_code,kind,parallel_units\n"
        "WLD-01,Welding 1,WELD-CELL,machine,1\n"
        "PNT-01,Paint line,PAINT,machine,1\n"
    ),
    "products.csv": (
        "sku,name,family,setup_family,sales_price_eur_cents,truly_variable_cost_eur_cents\n"
        "F-200,Frame,Frames,RAL9005,98000,43000\n"
    ),
    "routings.csv": (
        "sku,operation_seq,operation,resource_code,alternative_resource_codes,"
        "standard_setup_min,standard_run_min_per_unit\n"
        "F-200,20,Paint,PNT-01,,15,10.9\n"
        "F-200,10,Weld,WLD-01,,,9.0\n"
    ),
    "orders.csv": (
        "order_id,sku,quantity_units,due_at,status,released_at,shipped_at,material_ready_at\n"
        "SO-1,F-200,16,2026-10-20T16:00:00Z,released,2026-10-10T08:00:00Z,,\n"
    ),
    "events.csv": (
        "event_id,event_type,at,resource_code,station_code,order_id,operation_seq,"
        "quantity_units,scrap_units,down_reason_code,scrap_reason_code\n"
        "e1,start,2026-10-13T07:15:00Z,WLD-01,,SO-1,10,16,0,,\n"
        "e2,end,2026-10-13T09:50:00Z,WLD-01,,SO-1,10,16,0,,\n"
    ),
    "calendar.csv": (
        "resource_code,kind,start_at,end_at,covered\n"
        "PNT-01,shift,2026-10-13T04:00:00Z,2026-10-13T12:00:00Z,false\n"
        "PNT-01,break,2026-10-13T10:00:00Z,2026-10-13T10:30:00Z,true\n"
    ),
}


def write_plant(
    root: Path, skip: tuple[str, ...] = (), extra: dict[str, str] | None = None
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "plant.json").write_text(
        json.dumps({"plant_code": "PLANT-T", "name": "Tiny", "timezone_iana": "Europe/Amsterdam"})
    )
    for name, text in {**FILES, **(extra or {})}.items():
        if name not in skip:
            (root / name).write_text(text)
    return root


PlantWriter = Callable[..., Path]


@pytest.fixture
def plant_files() -> dict[str, str]:
    return dict(FILES)


@pytest.fixture
def make_plant(tmp_path: Path) -> PlantWriter:
    def make(
        name: str = "p", skip: tuple[str, ...] = (), extra: dict[str, str] | None = None
    ) -> Path:
        return write_plant(tmp_path / name, skip=skip, extra=extra)

    return make
