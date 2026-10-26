# ERP and MES export guide

For the plant's IT or ERP owner. It says which exports a diagnostic needs, what each must contain, and in which format. You do not have to rename columns: we map your names once and save the mapping (see `it-guide.md`).

## What to export

To start, three exports are enough: the event log, a steps list and a shift sheet. Every other export adds euros, actions or confidence (`data-checklist.md` lists what each adds).

| # | Export | Typical source in an ERP/MES | Period | Format | Need |
|---|---|---|---|---|---|
| 1 | Event log: start and finish per job and step (`mes_events`, or `scans` from a scan export) | MES start/finish/stop bookings, ERP hour bookings per operation, or scans at the bench | At least 8 weeks | CSV or Excel | Minimum |
| 2 | Steps list: machines, work centres and handmade benches (`werkplekken`, or `workstations`) | Work centre or resource master data, or a spreadsheet | Current | CSV or Excel | Minimum |
| 3 | Shift sheet: shifts per step, staffed positions at handmade steps (`rooster`, or `shift_plan`) | Roster or a spreadsheet per step | Same period + next weeks | CSV or Excel | Minimum |
| 4 | Jobs or orders with value and material cost (`orders`, or `jobs`) | Production or sales orders, open and closed | Last 8–12 weeks + open order book | CSV or Excel | Adds € lost, late orders |
| 5 | Products with sales price and truly variable cost (`artikelen`) | Item master + price list; variable cost from costing (materials, bought parts, outsourcing; not labour) | Current | CSV or Excel | Adds € per product |
| 6 | Routings with operations per step (`bewerkingen`) | Routing / operation master | Current, all active products | CSV or Excel | Adds the planned path and standard times |
| 7 | Shared teams and team sizes per shift (`teams`, `team_plan`) | Roster | Same period | CSV or Excel | Adds capacity of steps that share people |

Breaks and holidays usually come in the shift sheet; breaks add the stagger-breaks action and holidays the forecast. These also raise confidence but are not needed to start: overtime per step and week (`overuren`), capacity costs (`capaciteitskosten`), changeover times between setup families (`omsteltijden`), outsourcing prices (`uitbesteding`).

## Format

- One file per export, named as above (e.g. `orders.csv`), all files of one export uploaded together.
- First row: column names. One row per record. No totals or blank title rows.
- CSV with `;` as separator and `,` as decimal point is fine (Dutch Excel default); so is `.xlsx`.
- Dates and times as your system writes them (e.g. `13-10-2026 07:15`); tell us the format once. Times are local plant time; we convert to UTC.
- Codes as they are in your system (step codes, status codes, stop reasons). We translate them with code tables; an unknown code becomes a rejected row with its reason, never a guess.
- Money in euros with decimals (e.g. `980,00`).

## Sending new data

Send the event log again whenever you have new weeks; events already sent count once, so overlapping periods are fine. Send a steps list, shift sheet or order list again when it changes; the new one replaces the old one. A wrong file can be replaced, a row the import cannot read can be fixed in the app (the file stays as you sent it), and an upload can be deleted. `it-guide.md` says what each does.

## What not to export

Leave out employee names, badge numbers, who worked where and time per person. If an export contains such a column anyway (e.g. `Medewerker`), it is dropped while the file is read and never stored.

## Per ERP

### [FIRST ERP STACK]

To be written once the first ERP/MES stack is chosen (CLAUDE.md: one stack first, exports before live connections): which report, table or view gives each export above, and the filters to use. No vendor screenshots or proprietary material.

## Columns the standard mapping reads

Generated from `packages/connectors/mappings/generic/mapping.yaml`. If your columns are named differently, that is fine: the mapping is adjusted once per source system.

<!-- generated:columns -->

### `werkplekken.csv` (or `.xlsx`)

| Column | Required | Type | Fills |
|---|---|---|---|
| Afdeling | yes | str | stations.station_code, stations.name, resources.station_code |
| Werkplek | yes | str | resources.resource_code |
| Omschrijving | yes | str | resources.name |

### `artikelen.csv` (or `.xlsx`)

| Column | Required | Type | Fills |
|---|---|---|---|
| Artikel | yes | str | products.sku |
| Omschrijving | yes | str | products.name |
| Productgroep | yes | str | products.family |
| Kleurgroep | no | str | products.setup_family |
| Verkoopprijs | yes | eur_cents | products.sales_price_eur_cents |
| Variabele kosten | yes | eur_cents | products.truly_variable_cost_eur_cents |

### `bewerkingen.csv` (or `.xlsx`)

| Column | Required | Type | Fills |
|---|---|---|---|
| Artikel | yes | str | routings.sku |
| Bewerking nr | yes | int | routings.operation_seq |
| Bewerking | yes | str | routings.operation |
| Werkplek | yes | str | routings.resource_code |
| Alternatief | no | list | routings.alternative_resource_codes |
| Insteltijd (min) | no | decimal | routings.standard_setup_min |
| Stuktijd (min) | no | decimal | routings.standard_run_min_per_unit |

### `orders.csv` (or `.xlsx`)

| Column | Required | Type | Fills |
|---|---|---|---|
| Ordernummer | yes | str | orders.order_id |
| Artikel | yes | str | orders.sku |
| Aantal | yes | int | orders.quantity_units |
| Leverdatum | yes | datetime | orders.due_at |
| Status | yes | str | orders.status |
| Vrijgegeven | no | datetime | orders.released_at |
| Verzonden | no | datetime | orders.shipped_at |
| Materiaal gereed | no | datetime | orders.material_ready_at |

### `mes_events.csv` (or `.xlsx`)

| Column | Required | Type | Fills |
|---|---|---|---|
| Status | yes | str | events.event_type |
| Tijdstip | yes | datetime | events.at |
| Werkplek | no | str | events.resource_code |
| Afdeling | no | str | events.station_code |
| Bon | no | str | events.order_id |
| Bewerking | no | int | events.operation_seq |
| Aantal | no | int | events.quantity_units |
| Afkeur | no | int | events.scrap_units |
| Storingscode | no | str | events.down_reason_code |
| Afkeurcode | no | str | events.scrap_reason_code |

### `rooster.csv` (or `.xlsx`)

| Column | Required | Type | Fills |
|---|---|---|---|
| Werkplek | yes | str | calendar.resource_code |
| Type | yes | str | calendar.kind |
| Start | yes | datetime | calendar.start_at |
| Einde | yes | datetime | calendar.end_at |
| Overgenomen | no | bool | calendar.covered |

### `overuren.csv` (or `.xlsx`)

| Column | Required | Type | Fills |
|---|---|---|---|
| Werkplek | yes | str | overtime.resource_code |
| Jaar | yes | int | overtime.iso_year |
| Week | yes | int | overtime.iso_week |
| Overuren | yes | decimal | overtime.overtime_h |

### `capaciteitskosten.csv` (or `.xlsx`)

| Column | Required | Type | Fills |
|---|---|---|---|
| Werkplek | yes | str | capacity_costs.resource_code |
| Overwerk per uur | no | eur_cents | capacity_costs.overtime_eur_cents_per_h |
| Extra dienst | no | eur_cents | capacity_costs.extra_shift_eur_cents |

### `omsteltijden.csv` (or `.xlsx`)

| Column | Required | Type | Fills |
|---|---|---|---|
| Werkplek | yes | str | changeovers.resource_code |
| Van kleurgroep | yes | str | changeovers.from_setup_family |
| Naar kleurgroep | yes | str | changeovers.to_setup_family |
| Omsteltijd (min) | yes | decimal | changeovers.changeover_min |

### `uitbesteding.csv` (or `.xlsx`)

| Column | Required | Type | Fills |
|---|---|---|---|
| Bewerking | yes | str | outsourcing.operation |
| Prijs per stuk | yes | eur_cents | outsourcing.price_eur_cents_per_unit |

Columns dropped as personal data in this mapping: Medewerker.

<!-- /generated:columns -->
