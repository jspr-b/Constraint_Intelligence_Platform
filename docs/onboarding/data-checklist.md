# Data checklist for a diagnostic

_Generated from docs/input-data.md by scripts/gen_onboarding.py. Do not edit by hand._

What we need from your plant to find what limits your output and what it costs. Exports from your ERP, MES or spreadsheets are enough; we map your column names, you do not have to change them. Send new exports whenever you have them: new events are added (sent twice counts once), new lists replace the old ones, and the answer is recalculated by itself. A row the import cannot read can be fixed in the app; your file stays as you sent it.

## Minimum to start: the event log, a steps list and a shift sheet

1. **Event log: start and finish per job and step (8+ weeks)** (#12)
   - The event log: start and finish per job and step, at least 8 weeks (MES, ERP hour bookings or scans at the bench).
2. **Steps list: machines and handmade steps** (#3)
   - Your steps: machines, work centres and handmade benches, with the codes you use.
3. **Shift sheet: shifts with staffed positions, and team sizes when steps share people** (#16)
   - Shift times per step, with the number of staffed positions at handmade steps (a count, never who).

That is enough to find your bottleneck and its lost hours. Plant and stations (items 1–2) we fill in together at the kick-off.

## What each extra file adds

- **Jobs with value and material cost** (#9): € lost, late orders and on-time delivery
- **Products with price and truly variable cost** (#5): € per product and the best product mix
- **Routings and operations per step** (#4, #6): the planned path and standard times; higher confidence
- **Breaks and shift changes** (#17): the stagger-breaks action
- **Holidays and closures** (#19): the forecast
- **Shared teams and their sizes per shift** (#28): the capacity of steps that share people; send it with the shift sheet when steps share people

## Also helpful: raises confidence, not required to start

- Setup families (e.g. colour groups) and changeover times between them. (#7)
- When material is ready per order. (#11)
- Stops with their reason. (#13)
- Scrap: how many and at which step it was found. (#14)
- Planned maintenance per step. (#18)
- Overtime worked per step per week (never per person). (#20)
- What extra capacity costs: overtime per hour, an extra shift, outsourcing. (#21)
- The baseline period and who in finance signs off the results. (#22)
- A PIN per station screen (the screen belongs to the step, not a person). (#25)
- A scheduled export: SFTP drop or read-only database view. (#27)

## Never needed: personal data

Employee names, badge numbers, who worked at which station, time per person, wages. If an export contains such columns, they are dropped while the file is read and never stored.

## Appendix for IT: field names

| Item | What | Fields in the standard model | History |
|---|---|---|---|
| 1 | Plant | `plant_code`, `name`, `timezone_iana` |  |
| 2 | Stations | `station_code`, `name`, machines in it |  |
| 3 | Steps | `resource_code` (the plant's own short code, e.g. `PNT-01`, `WELD-BENCH`), `name`, `kind` (machine or handmade), `station_code`, `parallel_units` |  |
| 4 | Operations per step | `operation`, `resource_code`, ERP `standard_run_min_per_unit` and `standard_setup_min` (reference only), `alternative_resource_codes` |  |
| 5 | Products | `sku`, `family`, `sales_price_eur_cents`, `truly_variable_cost_eur_cents` (materials, bought parts, outsourcing; not labour) |  |
| 6 | Routings | `sku` → `operation_seq`, `operation`, `resource_code`, alternatives; second visits allowed |  |
| 7 | Setup families | colour/material family per product, changeover time between families |  |
| 8 | Code tables | ERP step codes → `resource_code`; status → event type; downtime and scrap reason codes |  |
| 9 | Jobs (orders): history + open order book | `order_id`, `sku` (optional), `quantity_units`, `due_at`, `released_at`, `shipped_at`, `status`, `order_value_eur_cents` and `material_cost_eur_cents` (optional) | at least 8 weeks |
| 11 | Material availability | `order_id`, `material_ready_at` |  |
| 12 | Event log (touchpoints) | `event_id`, `at`, `resource_code`, `order_id` (the job), `operation_seq` (optional), `event_type` (start, end, setup_start/end, down_start/end), `quantity_units` | at least 8 weeks |
| 13 | Downtime reasons | `down_reason_code` per stop |  |
| 14 | Scrap | `scrap_units`, operation where found |  |
| 16 | Shifts with positions | start/end per step per shift, staffed `positions` (a count) for handmade steps |  |
| 17 | Breaks and shift changes | start/end per step, whether covered |  |
| 18 | Maintenance windows | planned start/end per step |  |
| 19 | Holidays and closures | dates |  |
| 20 | Overtime worked | `overtime_h` per step per week |  |
| 28 | Shared teams | `team_code`, `name`, steps it covers; team size per shift (a count, never who) |  |
| 21 | Cost of extra capacity | overtime `eur_cents_per_h`, extra shift cost, outsourcing price per operation |  |
| 22 | Baseline agreement | baseline period, finance contact for sign-off |  |
| 24 | Personal accounts | `email`, `role`, `plant_code` |  |
| 25 | Station logins | station, PIN |  |
| 27 | Export connection | SFTP or read-only database view, schedule |  |
