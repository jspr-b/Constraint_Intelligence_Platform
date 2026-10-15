# ADR-0003: Provenance and missing data

- **Status:** Proposed
- **Date:** 2026-10-15
- **CLAUDE.md reference:** Hard constraints (no invented data, euros must be traceable), Recommendations and AI, Code rules

## Context

The product's credibility rests on its numbers. A plant director, a planner and finance must be able to ask "where does this € come from?" and get an answer. Real plant data has gaps; filling them with defaults would produce confident wrong answers.

## Decision

**Every computed number is a `Figure`:**

| Field | Meaning |
|---|---|
| `value` | The number, or a `Missing` |
| `unit` | Unit per ADR-0002 (`eur_cents`, `h`, `pct`, …) |
| `formula_id` | Registered formula with version, e.g. `throughput_per_unit_v1` |
| `inputs` | Named inputs: plain values or nested Figures |
| `period_start_at`, `period_end_at` | Data period the number covers |
| `confidence` | `high`, `medium`, `low` or `none` |

**Missing data is a `Missing`, never a default:** what is missing, why, and its impact on confidence. A Figure computed from a Missing input is itself Missing, or carries lower confidence when the formula can still be computed honestly.

**API envelope:** every numeric field in an API response is a Figure, so the UI can always show the formula and inputs behind a number.

**Language model boundary:** the language model never produces a Figure. It may rank and explain Figures the engine produced, and answer questions about them.

### Worked example (synthetic product Frame F-200)

```json
{
  "value": 55000,
  "unit": "eur_cents",
  "formula_id": "throughput_per_unit_v1",
  "inputs": {
    "sales_price_eur_cents": 98000,
    "truly_variable_cost_eur_cents": 43000
  },
  "period_start_at": "2026-07-20T00:00:00Z",
  "period_end_at": "2026-10-11T23:59:59Z",
  "confidence": "high"
}
```

Formula text in the registry: `throughput = sales price − truly variable cost` (throughput accounting, not cost-accounting margin). If the truly variable cost were missing, `value` would be a `Missing("truly_variable_cost_eur_cents", reason="not in products export", confidence_impact="high")`, and every € figure depending on it would show as missing too.

## Consequences

- Engine functions return Figures; plain floats do not leave the engine.
- The UI can offer "Trace" on any number at no extra cost.
- Figures are larger than plain numbers; frames stay plain Polars internally and only results are wrapped.
