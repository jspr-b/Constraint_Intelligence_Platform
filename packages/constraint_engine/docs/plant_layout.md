# Standard plant layout

A plant directory in the standard layout is what the engine reads. Connectors (ERP/MES/Excel)
write this layout; the diagnose CLI and tests read it. One directory = one plant.

| File | Required | One row per | Columns |
|---|---|---|---|
| `plant.json` | yes | — | `plant_code`, `name`, `timezone_iana` |
| `stations.csv` | yes | station | `station_code`, `name` |
| `resources.csv` | yes | machine | `resource_code`, `name`, `station_code`, `kind`, `parallel_units` |
| `products.csv` | yes | product | `sku`, `name`, `family`, `setup_family`, `sales_price_eur_cents`, `truly_variable_cost_eur_cents` |
| `routings.csv` | yes | routing step | `sku`, `operation_seq`, `operation`, `resource_code`, `alternative_resource_codes` (`;`-separated), `standard_setup_min`, `standard_run_min_per_unit` |
| `orders.csv` | yes | order | `order_id`, `sku`, `quantity_units`, `due_at`, `status`, `released_at`, `shipped_at`, `material_ready_at` |
| `events.csv` | yes | event | `event_id`, `event_type`, `at`, `resource_code`, `station_code`, `order_id`, `operation_seq`, `quantity_units`, `scrap_units`, `down_reason_code`, `scrap_reason_code` |
| `calendar.csv` | yes | calendar window | `resource_code`, `kind`, `start_at`, `end_at`, `covered` |
| `resource_operations.csv` | no | capability | `resource_code`, `operation`, `standard_run_min_per_unit` |
| `changeovers.csv` | no | changeover | `resource_code`, `from_setup_family`, `to_setup_family`, `changeover_min` |
| `overtime.csv` | no | machine-week | `resource_code`, `iso_year`, `iso_week`, `overtime_h` |
| `capacity_costs.csv` | no | machine | `resource_code`, `overtime_eur_cents_per_h`, `extra_shift_eur_cents` |
| `outsourcing.csv` | no | operation | `operation`, `sku`, `price_eur_cents_per_unit` |

Rules:

- Times are ISO 8601 with an offset (`2026-10-13T07:15:00Z`); values without an offset are rejected.
- Money is whole euro cents. Empty cells mean "not given".
- A missing required file is reported as missing, not as an error. Invalid rows are reported with their line number and reason; valid rows are still loaded.
- No column may identify a person. Connectors drop such columns before writing this layout.
