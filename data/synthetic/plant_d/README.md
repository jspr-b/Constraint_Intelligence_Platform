# plant_d: handmade bottleneck, no product data

A made-up metal workshop for ADR-0009 (steps and touchpoints). Never real customer data. It proves that the
bottleneck is found from steps and touchpoints alone: some steps are machines, some are handmade, two share one
team, and the plant sends no products and no routings.

## Steps

| Step code | Kind | Capacity per shift (early / late) | Notes |
|---|---|---|---|
| `LASER` | machine | 1 / 1 | Cuts every job |
| `PRESS` | machine | 1 / 1 | Bends most jobs; some skip it |
| `WELD-BENCH` | handmade | 3 / 3 positions | Hand welding |
| `ASSY-BENCH` | handmade | 4 / 3 positions | Hand assembly; some jobs come back for a second visit |
| `FINISH` | handmade | 3 / 3 positions | Grinding, cleaning and a visual check |
| `PACK` | handmade | 2 / 2 positions | Packing |

`FINISH` and `PACK` are covered by one team, `FINISH-TEAM`, of 3 on early shift and 2 on late shift. The team
is smaller than the positions it covers, so the team, not a single bench, limits output.

Two shifts, Monday to Friday (06:00–14:30 and 14:30–23:00 Europe/Amsterdam), four unstaggered breaks a day,
history 2026-07-20 to 2026-10-11 (12 weeks), like plants A, B and C.

## What the plant sends

- A steps list, a shift sheet with positions and team sizes, orders with job value and material cost, and one
  event log (job, step, time, what happened). File and column names differ from plant A, with their own mapping.
- No products, no routings, no standard times. A job's path comes from its touchpoint times.
- The event log has one personal column (`operator`), which must be dropped on import and never stored.
- Handmade steps record start and finish by scan. 4% of finish scans at handmade steps are forgotten on purpose,
  so the data is noisy the way real bench data is.

## Known answer

| Known answer | Value |
|---|---|
| What limits output | Team `FINISH-TEAM` (covers `FINISH` and `PACK`), internal |
| Agreement | At least 3 of the 4 methods point at the team or one of its steps |
| Confidence | Medium: lowered by the forgotten scans and by the path coming from history |
| Euros | From job value minus material cost (no products); per month within 2% of the generator log |
| Not the answer | No machine: `LASER` and `PRESS` are well below the team's load |

The exact busy shares and lost hours per month are written to `expected_answers.yaml` by the generator from its
own log (sequence 03 of CI0003), never from engine calculations. The rows above are fixed now and are not edited
to fit the code.
