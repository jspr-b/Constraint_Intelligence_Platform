# Standard plant layout

A plant directory in the standard layout is what the engine reads. Connectors (ERP/MES/Excel)
write this layout; a resource is a step, machine or handmade (ADR-0009); the diagnose CLI and tests read it. One directory = one plant.

| File | Required | One row per | Columns |
|---|---|---|---|
| `plant.json` | yes | — | `plant_code`, `name`, `timezone_iana` |
| `stations.csv` | yes | station | `station_code`, `name` |
| `resources.csv` | yes | step (machine or handmade) | `resource_code`, `name`, `station_code`, `kind` (`machine`, `manual`, `station`, `work_centre`), `parallel_units` |
| `products.csv` | no | product | `sku`, `name`, `family`, `setup_family`, `sales_price_eur_cents`, `truly_variable_cost_eur_cents` |
| `routings.csv` | no | routing step | `sku`, `operation_seq`, `operation`, `resource_code`, `alternative_resource_codes` (`;`-separated), `standard_setup_min`, `standard_run_min_per_unit` |
| `orders.csv` | yes | job | `order_id`, `sku` (optional), `quantity_units`, `due_at`, `status`, `released_at`, `shipped_at`, `material_ready_at`, `order_value_eur_cents`, `material_cost_eur_cents` |
| `events.csv` | yes | event | `event_id`, `event_type`, `at`, `resource_code`, `station_code`, `order_id`, `operation_seq`, `quantity_units`, `scrap_units`, `down_reason_code`, `scrap_reason_code` |
| `calendar.csv` | yes | calendar window | `resource_code`, `kind`, `start_at`, `end_at`, `covered`, `positions` (shifts: staffed positions, a count) |
| `resource_operations.csv` | no | capability | `resource_code`, `operation`, `standard_run_min_per_unit` |
| `changeovers.csv` | no | changeover | `resource_code`, `from_setup_family`, `to_setup_family`, `changeover_min` |
| `overtime.csv` | no | machine-week | `resource_code`, `iso_year`, `iso_week`, `overtime_h` |
| `capacity_costs.csv` | no | machine | `resource_code`, `overtime_eur_cents_per_h`, `extra_shift_eur_cents` |
| `outsourcing.csv` | no | operation | `operation`, `sku`, `price_eur_cents_per_unit` |
| `teams.csv` | no | team shared by steps | `team_code`, `name`, `resource_codes` (`;`-separated steps) |
| `team_shifts.csv` | no | team shift | `team_code`, `start_at`, `end_at`, `positions` (a count, never who) |

Rules:

- Times are ISO 8601 with an offset (`2026-10-13T07:15:00Z`); values without an offset are rejected.
- Money is whole euro cents. Empty cells mean "not given".
- A missing required file is reported as missing, not as an error. Invalid rows are reported with their line number and reason; valid rows are still loaded.
- No column may identify a person. Connectors drop such columns before writing this layout.
