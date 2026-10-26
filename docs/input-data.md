# Input data

The data the Constraint Intelligence Platform needs to operate, based on CLAUDE.md, the mockup pages and festival CI0001.

Field names follow the conventions in CLAUDE.md: units in the name, times in UTC, money in integer EUR cents.

**Need:** **Must** = required to start the paid diagnostic · **Should** = raises confidence, adds euros or is needed for pilot and daily use · **Later** = later pillars

A step is any place where work happens: a machine, a handmade bench, a check or packing (ADR-0009). A job is whatever moves through the steps (an order, batch or ticket).

You can send exports more than once (ADR-0010): a new event log adds to what is there (an event already sent is counted once), and a new steps list, shift sheet or order list replaces the earlier one. See "Sending data again, fixing and deleting" below.

## A. Plant structure (once, update when it changes)

| # | Data | Key fields | Source | Need | Used by |
|---|---|---|---|---|---|
| 1 | Plant | `plant_code`, `name`, `timezone_iana` | Plant setup | Must | Everything |
| 2 | Stations | `station_code`, `name`, machines in it | Plant setup | Must | Plant flow, shift page, station screens |
| 3 | Steps | `resource_code` (the plant's own short code, e.g. `PNT-01`, `WELD-BENCH`), `name`, `kind` (machine or handmade), `station_code`, `parallel_units` | ERP work centres, a steps list, or setup | Must | Everything |
| 4 | Operations per step | `operation`, `resource_code`, ERP `standard_run_min_per_unit` and `standard_setup_min` (reference only), `alternative_resource_codes` | ERP routings | Should | Standard times (performance), load, alternatives |
| 5 | Products | `sku`, `family`, `sales_price_eur_cents`, `truly_variable_cost_eur_cents` (materials, bought parts, outsourcing; not labour) | ERP + finance | Should | € per product (else from job value) |
| 6 | Routings | `sku` → `operation_seq`, `operation`, `resource_code`, alternatives; second visits allowed | ERP | Should | Planned path (else from touchpoint times), load, forecast |
| 7 | Setup families | colour/material family per product, changeover time between families | ERP or planner | Should | "Resequence setups" action |
| 8 | Code tables | ERP step codes → `resource_code`; status → event type; downtime and scrap reason codes | ERP/MES + mapping | Must | Import and mapping |

## B. Orders and demand (daily)

| # | Data | Key fields | Source | Need | Used by |
|---|---|---|---|---|---|
| 9 | Jobs (orders): history + open order book | `order_id`, `sku` (optional), `quantity_units`, `due_at`, `released_at`, `shipped_at`, `status`, `order_value_eur_cents` and `material_cost_eur_cents` (optional) | ERP | Should · ≥ 8–12 weeks back and ahead | € lost (from job value), late orders, on-time %, backlog, forecast |
| 10 | Demand forecast beyond open orders | `sku`, `week`, `quantity_units` | Sales / ERP | Later | Forecast after the order book runs out |
| 11 | Material availability | `order_id`, `material_ready_at` | ERP / MRP | Should | Detecting "material is the constraint" |

## C. What happens on the floor (continuous)

| # | Data | Key fields | Source | Need | Used by |
|---|---|---|---|---|---|
| 12 | Event log (touchpoints) | `event_id`, `at`, `resource_code`, `order_id` (the job), `operation_seq` (optional), `event_type` (start, end, setup_start/end, down_start/end), `quantity_units` | MES, ERP hour bookings, scans at the bench, or the station screen | Must · ≥ 8 weeks | Detection, task times, states, lost hours |
| 13 | Downtime reasons | `down_reason_code` per stop | MES / station screen | Should | Loss by cause, maintenance action |
| 14 | Scrap | `scrap_units`, operation where found | MES / quality system | Should | Loss by cause, "inspect before constraint" action |
| 15 | Move and scan events | `event_type` move/scan per station | MES / station screen | Later | Transitions and touchpoints views |

## D. Capacity (weekly, or when it changes)

| # | Data | Key fields | Source | Need | Used by |
|---|---|---|---|---|---|
| 16 | Shifts with positions | start/end per step per shift, staffed `positions` (a count) for handmade steps | Roster / shift sheet | Must | Capacity, calendar |
| 17 | Breaks and shift changes | start/end per step, whether covered | Roster | Should | "Stagger breaks" action |
| 18 | Maintenance windows | planned start/end per step | Maintenance plan | Should | "Move maintenance" action |
| 19 | Holidays and closures | dates | HR / planning | Should | Forecast |
| 20 | Overtime worked | `overtime_h` per step per week | Time registration, per step only | Should | "Overtime on non-constraints" signal |
| 28 | Shared teams | `team_code`, `name`, steps it covers; team size per shift (a count, never who) | Roster / shift sheet | Should | Capacity of steps that share people; a team as the bottleneck |

## E. Money for decisions and proof

| # | Data | Key fields | Source | Need | Used by |
|---|---|---|---|---|---|
| 21 | Cost of extra capacity | overtime `eur_cents_per_h`, extra shift cost, outsourcing price per operation | Finance | Should | Elevate actions (gain vs cost) |
| 22 | Baseline agreement | baseline period, finance contact for sign-off | Agreed in the diagnostic | Should | Value report |
| 23 | Subscription price | `eur_cents_per_month` | Contract | Later | "Gain ≥ 5× subscription" |

## F. People and access (accounts only, nothing about floor work)

| # | Data | Key fields | Source | Need | Used by |
|---|---|---|---|---|---|
| 24 | Personal accounts | `email`, `role`, `plant_code` | IT | Must for the platform, not for the diagnostic | Login, users, access |
| 25 | Station logins | station, PIN | IT | Should | Station screen |
| 26 | Single sign-on | Microsoft Entra ID tenant details | IT | Later | Login |
| 27 | Export connection | SFTP or read-only database view, schedule | IT | Should (pilot) | Connections, scheduled import |

## Never imported or stored

Employee names, badge numbers, who worked at which station, time per person, wages per person. If an export contains them, the columns are dropped on import (CLAUDE.md hard constraint; Dutch Works Councils Act art. 27).

## Minimum to start a paid diagnostic

1 event log + 1 steps list + 1 shift sheet:

1. Event log: start and finish per job and step, for at least 8 weeks (#12)
2. Steps list: every step's code and name, machine or handmade (#3)
3. Shift sheet: shifts per step, with staffed positions for handmade steps (#16), and team sizes when steps share people (#28)

That is enough to find the bottleneck and its lost hours. Each extra file adds something:

| Add | What it adds |
|---|---|
| Jobs with value and material cost (#9) | € lost, late orders and on-time delivery |
| Products with price and truly variable cost (#5) | € per product, best product mix |
| Routings and operations per step (#4, #6) | the planned path and standard times; higher confidence |
| Breaks (#17) | the "stagger breaks" action |
| Holidays (#19) | the forecast |
| Shared teams (#28) | capacity of steps that share people; send it with the shift sheet when steps share people, or a shared team can never be found |

Plant and stations (#1–2) are filled in together during kick-off. Everything else raises confidence but is not required. Missing data is shown as missing, never filled in by guessing.

## How data comes in

| Stage | How | When |
|---|---|---|
| 1. File upload | CSV/Excel exports on the Import page, mapped once and saved | Diagnostic and MVP |
| 2. Scheduled export | Same files nightly/hourly via SFTP, or a read-only database view | Pilot |
| 3. Live connections | ERP APIs, machine signals via OPC UA / MQTT | Later |

All stages end in the same standard data model. Plants without MES or ERP hour bookings can use the station screen to capture start, done and stop events per machine.

## Sending data again, fixing and deleting

Your files are the source; the platform keeps every upload as a history you manage (ADR-0010).

| What you do | What happens |
|---|---|
| Upload a new export (Import page) | Nothing changes until you run it. The page first shows what it will change: events added, events already there, lists replaced. |
| Run it | A new event log **adds** to what is there; an event sent before counts once. A new steps list, shift sheet, order list or product list **replaces** the earlier one. The answer is recalculated by itself. |
| Replace or add a file in an upload | Before the run the upload changes; after it, a **new version** takes the old one's place, and the old one stays in the history as *replaced*. |
| Fix a row the import could not read | IT or the planner types the right value (or leaves the row out) with a reason. The file stays as sent; the fix is stored next to the original, with who and when, and can be undone. Data quality lists every fix, also as a CSV for the ERP owner. |
| Delete an upload or import | Gone for good: its files, rows, fixes and numbers. One history line says who deleted it and when. The plant is rebuilt from the other uploads; a confirmation shows first what changes. IT can delete all data of a plant with the plant code typed. |
| Change Plant setup or the Capacity calendar | The answer is recalculated by itself. |

Every page shows a banner while the answer is recalculated, why, when the numbers are from, and how old the newest data is (older than 7 days: upload new events). By default IT and the planner upload, fix and delete; only IT deletes all data of a plant; the COO can change this on the Access page.
