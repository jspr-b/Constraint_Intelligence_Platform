# Data checklist for a diagnostic

_Generated from docs/input-data.md by scripts/gen_onboarding.py. Do not edit by hand._

What we need from your plant to find what limits your output and what it costs. Exports from your ERP and MES are enough; we map your column names, you do not have to change them.

## Minimum to start: 5 exports and 1 sheet

1. **Orders** (#9)
   - Orders: the last 8–12 weeks and the open order book, with due dates.
2. **Routings and operations per machine** (#4, #6)
   - Which operations each machine can do, with the ERP standard times.
   - Routings: the steps each product goes through, in order, per machine.
3. **Products with price and truly variable cost** (#5)
   - Products with sales price and truly variable cost (materials, bought parts, outsourcing; not labour).
4. **Start and finish bookings (8+ weeks)** (#12)
   - Start and finish bookings per order and machine, at least 8 weeks (MES or ERP hour bookings).
5. **Shifts, breaks and holidays (one sheet)** (#16, #17, #19)
   - Shift times per machine.
   - Breaks and shift changes, and whether a machine keeps running during them.
   - Holidays and plant closures.

Plant, stations and machines (items 1–3) we fill in together at the kick-off.

## Also helpful: raises confidence, not required to start

- Setup families (e.g. colour groups) and changeover times between them. (#7)
- When material is ready per order. (#11)
- Machine stops with their reason. (#13)
- Scrap: how many and at which step it was found. (#14)
- Planned maintenance per machine. (#18)
- Overtime worked per machine per week (never per person). (#20)
- What extra capacity costs: overtime per hour, an extra shift, outsourcing. (#21)
- The baseline period and who in finance signs off the results. (#22)
- A PIN per station screen (the screen belongs to the machine, not a person). (#25)
- A scheduled export: SFTP drop or read-only database view. (#27)

## Never needed: personal data

Employee names, badge numbers, who worked at which station, time per person, wages. If an export contains such columns, they are dropped while the file is read and never stored.

## Appendix for IT: field names

| Item | What | Fields in the standard model | History |
|---|---|---|---|
| 1 | Plant | `plant_code`, `name`, `timezone_iana` |  |
| 2 | Stations | `station_code`, `name`, machines in it |  |
| 3 | Machines | `resource_code` (e.g. `PNT-01`), `name`, `station_code`, `parallel_units` |  |
| 4 | Operations per machine | `operation`, `resource_code`, ERP `standard_run_min_per_unit` and `standard_setup_min` (reference only), `alternative_resource_codes` |  |
| 5 | Products | `sku`, `family`, `sales_price_eur_cents`, `truly_variable_cost_eur_cents` (materials, bought parts, outsourcing; not labour) |  |
| 6 | Routings | `sku` → `operation_seq`, `operation`, `resource_code`, alternatives; second visits allowed |  |
| 7 | Setup families | colour/material family per product, changeover time between families |  |
| 8 | Code tables | ERP machine codes → `resource_code`; status → event type; downtime and scrap reason codes |  |
| 9 | Orders: history + open order book | `order_id`, `sku`, `quantity_units`, `due_at`, `released_at`, `shipped_at`, `status` | at least 8 weeks |
| 11 | Material availability | `order_id`, `material_ready_at` |  |
| 12 | Operation events | `event_id`, `at`, `resource_code`, `order_id`, `operation_seq`, `event_type` (start, end, setup_start/end, down_start/end), `quantity_units` | at least 8 weeks |
| 13 | Downtime reasons | `down_reason_code` per stop |  |
| 14 | Scrap | `scrap_units`, operation where found |  |
| 16 | Shifts | start/end per machine per weekday |  |
| 17 | Breaks and shift changes | start/end per machine, whether covered |  |
| 18 | Maintenance windows | planned start/end per machine |  |
| 19 | Holidays and closures | dates |  |
| 20 | Overtime worked | `overtime_h` per machine per week |  |
| 21 | Cost of extra capacity | overtime `eur_cents_per_h`, extra shift cost, outsourcing price per operation |  |
| 22 | Baseline agreement | baseline period, finance contact for sign-off |  |
| 24 | Personal accounts | `email`, `role`, `plant_code` |  |
| 25 | Station logins | station, PIN |  |
| 27 | Export connection | SFTP or read-only database view, schedule |  |
