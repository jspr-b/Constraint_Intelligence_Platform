"""Turn a synthetic plant into messy ERP/MES-style exports, to test import against.

Output looks like what a Dutch plant would send: Dutch column names, ERP machine codes,
local timestamps (``dd-mm-jjjj uu:mm``), prices in euros with a decimal comma, and an employee
column with fake values that the import must drop. Every file is written as CSV and as .xlsx.
A defect variant adds known problems for the data quality report.

``uv run python -m constraint_engine.synthetic.erp_export <plant dir> <out dir>``
"""

import csv
import json
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from openpyxl import Workbook

# ERP machine code per standard resource code (also documented in data/synthetic/README.md).
ERP_CODE = {
    "CUT-01": "SNIJ1",
    "WLD-01": "LAS1",
    "WLD-02": "LAS2",
    "PNT-01": "LAK1",
    "ASM-01": "MONT1",
    "PCK-01": "INPAK1",
}
MES_STATUS = {
    "start": "GESTART",
    "end": "GEREED",
    "setup_start": "OMSTEL_START",
    "setup_end": "OMSTEL_EINDE",
    "down_start": "STORING_START",
    "down_end": "STORING_EINDE",
    "scrap": "AFKEUR",
    "scan": "AANKOMST",
    "move": "VERTREK",
}
ORDER_STATUS = {
    "open": "Open",
    "released": "Vrijgegeven",
    "in_progress": "In bewerking",
    "shipped": "Verzonden",
}
CALENDAR_KIND = {
    "shift": "Dienst",
    "break": "Pauze",
    "maintenance": "Onderhoud",
    "holiday": "Feestdag",
}
FAKE_EMPLOYEES = [f"TEST-MEDEWERKER-{n:02d}" for n in range(1, 7)]
"""Clearly fake values: the import must drop this column, never store it."""

Row = dict[str, Any]


def _rows(path: Path) -> list[Row]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


class Exporter:
    def __init__(self, plant_dir: Path) -> None:
        self.src = plant_dir
        tz = json.loads((plant_dir / "plant.json").read_text())["timezone_iana"]
        self.tz = ZoneInfo(tz)
        self.rng = random.Random(2026)

    def local(self, iso: str) -> datetime | None:
        if not iso:
            return None
        moment = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(self.tz)
        # ERP exports show local time to the minute; CSV and xlsx carry the same value.
        return moment.replace(tzinfo=None, second=0, microsecond=0)

    @staticmethod
    def euros(cents: str) -> str:
        if not cents:
            return ""
        value = int(cents) / 100
        return f"{value:.2f}".replace(".", ",")

    def machines(self) -> list[Row]:
        stations = {r["station_code"]: r["name"] for r in _rows(self.src / "stations.csv")}
        return [
            {
                "Werkplek": ERP_CODE[r["resource_code"]],
                "Omschrijving": r["name"],
                "Afdeling": stations[r["station_code"]],
            }
            for r in _rows(self.src / "resources.csv")
        ]

    def products(self) -> list[Row]:
        return [
            {
                "Artikel": r["sku"],
                "Omschrijving": r["name"],
                "Productgroep": r["family"],
                "Kleurgroep": r["setup_family"],
                "Verkoopprijs": self.euros(r["sales_price_eur_cents"]),
                "Variabele kosten": self.euros(r["truly_variable_cost_eur_cents"]),
            }
            for r in _rows(self.src / "products.csv")
        ]

    def routings(self) -> list[Row]:
        return [
            {
                "Artikel": r["sku"],
                "Bewerking nr": f"{int(r['operation_seq']):03d}",
                "Bewerking": r["operation"],
                "Werkplek": ERP_CODE[r["resource_code"]],
                "Alternatief": ";".join(
                    ERP_CODE[a] for a in r["alternative_resource_codes"].split(";") if a
                ),
                "Insteltijd (min)": r["standard_setup_min"].replace(".", ","),
                "Stuktijd (min)": r["standard_run_min_per_unit"].replace(".", ","),
            }
            for r in _rows(self.src / "routings.csv")
        ]

    def orders(self) -> list[Row]:
        return [
            {
                "Ordernummer": r["order_id"].removeprefix("SO-"),
                "Artikel": r["sku"],
                "Aantal": r["quantity_units"],
                "Leverdatum": self.local(r["due_at"]),
                "Status": ORDER_STATUS[r["status"]],
                "Vrijgegeven": self.local(r["released_at"]),
                "Verzonden": self.local(r["shipped_at"]),
                "Materiaal gereed": self.local(r["material_ready_at"]),
            }
            for r in _rows(self.src / "orders.csv")
        ]

    def events(self) -> list[Row]:
        stations = {r["station_code"]: r["name"] for r in _rows(self.src / "stations.csv")}
        out = []
        for r in _rows(self.src / "events.csv"):
            out.append(
                {
                    "Werkplek": ERP_CODE.get(r["resource_code"], ""),
                    "Afdeling": stations.get(r["station_code"], ""),
                    "Bon": r["order_id"].removeprefix("SO-"),
                    "Bewerking": f"{int(r['operation_seq']):03d}" if r["operation_seq"] else "",
                    "Status": MES_STATUS[r["event_type"]],
                    "Tijdstip": self.local(r["at"]),
                    "Aantal": r["quantity_units"],
                    "Afkeur": r["scrap_units"],
                    "Storingscode": r["down_reason_code"],
                    "Afkeurcode": r["scrap_reason_code"],
                    "Medewerker": self.rng.choice(FAKE_EMPLOYEES),
                }
            )
        return out

    def roster(self) -> list[Row]:
        return [
            {
                "Werkplek": ERP_CODE[r["resource_code"]],
                "Type": CALENDAR_KIND[r["kind"]],
                "Start": self.local(r["start_at"]),
                "Einde": self.local(r["end_at"]),
                "Overgenomen": "ja" if r["covered"] == "true" else "nee",
            }
            for r in _rows(self.src / "calendar.csv")
        ]

    def extras(self) -> dict[str, list[Row]]:
        return {
            "overuren": [
                {
                    "Werkplek": ERP_CODE[r["resource_code"]],
                    "Jaar": r["iso_year"],
                    "Week": r["iso_week"],
                    "Overuren": r["overtime_h"].replace(".", ","),
                }
                for r in _rows(self.src / "overtime.csv")
            ],
            "capaciteitskosten": [
                {
                    "Werkplek": ERP_CODE[r["resource_code"]],
                    "Overwerk per uur": self.euros(r["overtime_eur_cents_per_h"]),
                    "Extra dienst": self.euros(r["extra_shift_eur_cents"]),
                }
                for r in _rows(self.src / "capacity_costs.csv")
            ],
            "omsteltijden": [
                {
                    "Werkplek": ERP_CODE[r["resource_code"]],
                    "Van kleurgroep": r["from_setup_family"],
                    "Naar kleurgroep": r["to_setup_family"],
                    "Omsteltijd (min)": r["changeover_min"].replace(".", ","),
                }
                for r in _rows(self.src / "changeovers.csv")
            ],
            "uitbesteding": [
                {
                    "Bewerking": r["operation"],
                    "Prijs per stuk": self.euros(r["price_eur_cents_per_unit"]),
                }
                for r in _rows(self.src / "outsourcing.csv")
            ],
        }

    def tables(self) -> dict[str, list[Row]]:
        return {
            "werkplekken": self.machines(),
            "artikelen": self.products(),
            "bewerkingen": self.routings(),
            "orders": self.orders(),
            "mes_events": self.events(),
            "rooster": self.roster(),
            **self.extras(),
        }


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%d-%m-%Y %H:%M")
    return str(value)


def write_tables(tables: dict[str, list[Row]], out: Path) -> None:
    """Each table as ``<name>.csv`` (semicolon, Dutch Excel style) and ``<name>.xlsx``."""
    (out / "csv").mkdir(parents=True, exist_ok=True)
    (out / "xlsx").mkdir(parents=True, exist_ok=True)
    for name, rows in tables.items():
        columns = list(rows[0]) if rows else []
        with (out / "csv" / f"{name}.csv").open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh, delimiter=";", lineterminator="\n")
            writer.writerow(columns)
            writer.writerows([_cell(r[c]) for c in columns] for r in rows)
        wb = Workbook()
        ws = wb.active
        assert ws is not None
        ws.title = name[:31]
        ws.append(columns)
        for r in rows:
            ws.append([r[c] if r[c] != "" else None for c in columns])
        wb.properties.created = wb.properties.modified = datetime(2026, 10, 15)
        wb.save(out / "xlsx" / f"{name}.xlsx")


def with_defects(
    tables: dict[str, list[Row]], rng: random.Random
) -> tuple[dict[str, list[Row]], dict[str, int]]:
    """Known problems: missing end times, unknown machine codes, scrap not recorded."""
    events = [dict(r) for r in tables["mes_events"]]
    ends = [i for i, r in enumerate(events) if r["Status"] == "GEREED"]
    drop = set(rng.sample(ends, max(1, len(ends) // 50)))
    scrap = {i for i, r in enumerate(events) if r["Status"] == "AFKEUR"}
    candidates = [i for i in range(len(events)) if i not in drop | scrap and events[i]["Werkplek"]]
    unknown = rng.sample(candidates, 25)
    for i in unknown:
        events[i]["Werkplek"] = "LAS9"
    events = [r for i, r in enumerate(events) if i not in drop | scrap]
    defects = {
        "missing_end_events": len(drop),
        "unknown_machine_code_rows": len(unknown),
        "scrap_rows_removed": len(scrap),
    }
    return {**tables, "mes_events": events}, defects


def export(plant_dir: Path | str, out: Path | str) -> Path:
    exporter = Exporter(Path(plant_dir))
    tables = exporter.tables()
    root = Path(out)
    write_tables(tables, root / "clean")
    defective, defects = with_defects(tables, random.Random(4242))
    write_tables(defective, root / "defects")
    (root / "defects" / "defects.json").write_text(
        json.dumps(defects, indent=2, sort_keys=True) + "\n"
    )
    (root / "erp_codes.json").write_text(json.dumps(ERP_CODE, indent=2, sort_keys=True) + "\n")
    return root


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print("usage: python -m constraint_engine.synthetic.erp_export <plant dir> <out dir>")
        return 2
    print(f"wrote {export(args[0], args[1])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
