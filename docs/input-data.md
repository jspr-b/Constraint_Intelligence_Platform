# Input data

The data the Constraint Intelligence Platform needs to operate, based on CLAUDE.md, the mockup pages and festival CI0001.

Field names follow the conventions in CLAUDE.md: units in the name, times in UTC, money in integer EUR cents.

**Need:** **Must** = required for the paid diagnostic · **Should** = pilot and daily use · **Later** = later pillars

## A. Plant structure (once, update when it changes)

| # | Data | Key fields | Source | Need | Used by |
|---|---|---|---|---|---|
| 1 | Plant | `plant_code`, `name`, `timezone_iana` | Plant setup | Must | Everything |
| 2 | Stations | `station_code`, `name`, machines in it | Plant setup | Must | Plant flow, shift page, station screens |
| 3 | Machines | `resource_code` (e.g. `PNT-01`), `name`, `station_code`, `parallel_units` | ERP work centres / setup | Must | Everything |
| 4 | Operations per machine | `operation`, `resource_code`, ERP `standard_run_min_per_unit` and `standard_setup_min` (reference only), `alternative_resource_codes` | ERP routings | Must | Plant setup, load, alternatives |
| 5 | Products | `sku`, `family`, `sales_price_eur_cents`, `truly_variable_cost_eur_cents` (materials, bought parts, outsourcing; not labour) | ERP + finance | Must | Every € figure |
| 6 | Routings | `sku` → `operation_seq`, `operation`, `resource_code`, alternatives; second visits allowed | ERP | Must | Load, backlog, forecast |
| 7 | Setup families | colour/material family per product, changeover time between families | ERP or planner | Should | "Resequence setups" action |
| 8 | Code tables | ERP machine codes → `resource_code`; status → event type; downtime and scrap reason codes | ERP/MES + mapping | Must | Import and mapping |

## B. Orders and demand (daily)

| # | Data | Key fields | Source | Need | Used by |
|---|---|---|---|---|---|
| 9 | Orders: history + open order book | `order_id`, `sku`, `quantity_units`, `due_at`, `released_at`, `shipped_at`, `status` | ERP | Must · ≥ 8–12 weeks back and ahead | Backlog, late orders, on-time %, forecast |
| 10 | Demand forecast beyond open orders | `sku`, `week`, `quantity_units` | Sales / ERP | Later | Forecast after the order book runs out |
| 11 | Material availability | `order_id`, `material_ready_at` | ERP / MRP | Should | Detecting "material is the constraint" |

## C. What happens on the floor (continuous)

| # | Data | Key fields | Source | Need | Used by |
|---|---|---|---|---|---|
| 12 | Operation events | `event_id`, `at`, `resource_code`, `order_id`, `operation_seq`, `event_type` (start, end, setup_start/end, down_start/end), `quantity_units` | MES, ERP hour bookings, or the station screen | Must · ≥ 8 weeks | Detection, task times, states, loss |
| 13 | Downtime reasons | `down_reason_code` per stop | MES / station screen | Should | Loss by cause, maintenance action |
| 14 | Scrap | `scrap_units`, operation where found | MES / quality system | Should | Loss by cause, "inspect before constraint" action |
| 15 | Move and scan events | `event_type` move/scan per station | MES / station screen | Later | Transitions and touchpoints views |

## D. Capacity (weekly, or when it changes)

| # | Data | Key fields | Source | Need | Used by |
|---|---|---|---|---|---|
| 16 | Shifts | start/end per machine per weekday | Roster / spreadsheet | Must | Capacity, calendar |
| 17 | Breaks and shift changes | start/end per machine, whether covered | Roster | Must | "Stagger breaks" action |
| 18 | Maintenance windows | planned start/end per machine | Maintenance plan | Should | "Move maintenance" action |
| 19 | Holidays and closures | dates | HR / planning | Must | Forecast |
| 20 | Overtime worked | `overtime_h` per machine per week | Time registration, per machine only | Should | "Overtime on non-constraints" signal |

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

5 exports + 1 sheet:

1. Orders (#9)
2. Routings and operations per machine (#4, #6)
3. Products with sales price and truly variable cost (#5)
4. Operation events for at least 8 weeks (#12)
5. Shifts, breaks and holidays (#16, #17, #19)

Machines and stations (#1–3) are filled in together during kick-off. Everything else raises confidence but is not required.

## How data comes in

| Stage | How | When |
|---|---|---|
| 1. File upload | CSV/Excel exports on the Import page, mapped once and saved | Diagnostic and MVP |
| 2. Scheduled export | Same files nightly/hourly via SFTP, or a read-only database view | Pilot |
| 3. Live connections | ERP APIs, machine signals via OPC UA / MQTT | Later |

All stages end in the same standard data model. Plants without MES or ERP hour bookings can use the station screen to capture start, done and stop events per machine.
