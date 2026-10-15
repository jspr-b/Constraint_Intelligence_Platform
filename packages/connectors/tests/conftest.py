"""Shared fixtures for connector tests: plant A paths and an events-only mapping."""

from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
PLANT_A = ROOT / "data" / "synthetic" / "plant_a"
EXPORT = PLANT_A / "erp_export" / "clean" / "csv"

EVENTS_MAPPING = yaml.safe_load(
    """
source_system: TEST-NL
timezone: Europe/Amsterdam
decimal: ","
delimiter: ";"
datetime_format: "%d-%m-%Y %H:%M"
personal_columns: [Medewerker]
code_tables:
  resource: {SNIJ1: CUT-01, LAS1: WLD-01, LAS2: WLD-02, LAK1: PNT-01, MONT1: ASM-01, INPAK1: PCK-01}
  station:
    {Cutting: CUTTING, Welding cell: WELD-CELL, Paint: PAINT, Assembly: ASSEMBLY, Packing: PACKING}
  status:
    {GESTART: start, GEREED: end, OMSTEL_START: setup_start, OMSTEL_EINDE: setup_end,
     STORING_START: down_start, STORING_EINDE: down_end, AFKEUR: scrap, AANKOMST: scan,
     VERTREK: move}
tables:
  - source: mes_events
    target: events
    fields:
      event_id: {generate: row_id}
      event_type: {from: Status, code_table: status}
      at: {from: Tijdstip, type: datetime}
      resource_code: {from: Werkplek, code_table: resource, optional: true}
      station_code: {from: Afdeling, code_table: station, optional: true}
      order_id: {from: Bon, prefix: "SO-", optional: true}
      operation_seq: {from: Bewerking, type: int, optional: true}
      quantity_units: {from: Aantal, type: int, optional: true}
      scrap_units: {from: Afkeur, type: int, optional: true}
      down_reason_code: {from: Storingscode, optional: true}
      scrap_reason_code: {from: Afkeurcode, optional: true}
"""
)


@pytest.fixture
def events_mapping() -> dict[str, Any]:
    return dict(EVENTS_MAPPING)
