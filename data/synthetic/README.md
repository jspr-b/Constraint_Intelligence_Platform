# Synthetic plants

Made-up plants with known answers, for tests and demos. Never real customer data.

Each plant directory holds:

- `config.yaml`: the plant design (machines, routings, products and demand, shifts, breaks, maintenance, breakdowns, scrap, costs, seed)
- the standard layout (`plant.json`, `*.csv`): what the engine reads, see `packages/constraint_engine/docs/plant_layout.md`
- `generator_log.json`: the simulation's own record of every machine's time, split into breaks, maintenance, breakdowns, running, setup, blocked and starved, in total and per month
- `expected_answers.yaml`: the known answers, derived only from the config and the generator log, never from engine calculations

Regenerate a plant (same seed, byte-identical output):

```bash
uv run python -m constraint_engine.synthetic data/synthetic/plant_a/config.yaml data/synthetic/plant_a
```

`packages/constraint_engine/tests/test_synthetic_plants.py` checks that regeneration reproduces the committed files, that every plant loads with zero row errors, and that the answers below hold.

All three plants share six machines in five stations: `CUT-01` laser cutting (also marks housings on a second visit), `WLD-01` and `WLD-02` in one welding cell (frames can go to either; `WLD-02` also grinds rails), `PNT-01` paint line, `ASM-01` assembly (also tests housings), `PCK-01` packing. Two shifts, four unstaggered breaks a day, history 2026-07-20 to 2026-10-11 (12 weeks), plus a 12-week open order book.

## plant_a: known constraint

Demand is above the paint line's capacity. The paint line stops for every break, changes colour often (25 min per colour change), has 90 minutes of planned maintenance inside production hours every Tuesday and random breakdowns. Scrap is only found at assembly, after the paint line. Plant A starts with one week of orders already on the floor.

| Known answer | Value |
|---|---|
| Constraint | `PNT-01`, internal |
| Utilisation (running + setup ÷ available) | PNT-01 99.9%; next highest WLD-01 34.8% |
| Throughput per paint-line hour | F-200 €2,000 · H-12 €1,854.55 · B-40 €1,800 · C-3 €1,533.33 · R-8 none (skips painting) |
| Lost paint-line hours, September 2026 | breaks 33.0 · setups 41.1 · breakdowns 6.2 · maintenance 7.5 · scrap 2.4 · starved 0 · blocked 0 |
| Constraint moves in the order book | no |

It also contains every Must and Should input from `docs/input-data.md`: downtime reasons, scrap with reason, setup families and changeovers, overtime worked per machine, capacity costs and an outsourcing price.

## plant_b: no internal constraint

The same plant with much less demand. Every machine has spare capacity, so output follows orders.

| Known answer | Value |
|---|---|
| Constraint | `none`, market-bound |
| Highest utilisation | PNT-01 42.1% (below the 85% threshold) |
| Orders | 212 released, 212 shipped |

The engine must say "no internal constraint" here instead of naming a machine.

## plant_c: the constraint moves

History is like plant A (paint line binding). From order-book week 7 a weld-heavy chassis (`K-50`, 22 min per unit on `WLD-02`, 5 min on paint) takes over the mix.

| Known answer | Value |
|---|---|
| Constraint in history | `PNT-01`, utilisation 99.9% |
| Constraint moves | to `WLD-02` in order-book week 7 (ISO week 2026-W48) |

## How the answers are defined

- **Constraint:** the machine with the highest share of available time spent running or in setup. If that share is below 85% everywhere, there is no internal constraint.
- **Lost constraint hours:** every shift minute of the constraint that did not produce good units, by cause.
- **Forecast load:** for each order-book week, run plus setup minutes of the orders created that week ÷ available minutes (shifts minus uncovered breaks minus planned maintenance; random breakdowns are not forecast). The binding machine is the highest-loaded one if it is at least 85%.

## plant_a/erp_export: messy exports to test import

Plant A as an ERP and MES would export it, generated from the plant files:

```bash
uv run python -m constraint_engine.synthetic.erp_export data/synthetic/plant_a data/synthetic/plant_a/erp_export
```

- `clean/csv/*.csv` (semicolon-separated, Dutch Excel style) and `clean/xlsx/*.xlsx`: the same 10 tables (`werkplekken`, `artikelen`, `bewerkingen`, `orders`, `mes_events`, `rooster`, `overuren`, `capaciteitskosten`, `omsteltijden`, `uitbesteding`)
- Dutch column names, local timestamps `dd-mm-jjjj uu:mm`, prices like `980,00`, order numbers without the `SO-` prefix
- `Medewerker` column with fake values `TEST-MEDEWERKER-01..06`: the import must drop it and never store it
- `defects/`: the same tables with known problems, counted in `defects/defects.json` (42 missing end events, 25 rows with unknown machine code `LAS9`, all 36 scrap rows removed)

ERP machine codes (`erp_codes.json`):

| ERP code | Standard code |
|---|---|
| SNIJ1 | CUT-01 |
| LAS1 | WLD-01 |
| LAS2 | WLD-02 |
| LAK1 | PNT-01 |
| MONT1 | ASM-01 |
| INPAK1 | PCK-01 |

MES statuses: `GESTART` start, `GEREED` end, `OMSTEL_START`/`OMSTEL_EINDE` setup, `STORING_START`/`STORING_EINDE` down, `AFKEUR` scrap, `AANKOMST` scan, `VERTREK` move.
