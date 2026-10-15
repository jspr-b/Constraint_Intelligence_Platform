# ADR-0002: Units, money and time

- **Status:** Proposed
- **Date:** 2026-10-15
- **CLAUDE.md reference:** Conventions

## Context

Constraint figures mix minutes, hours, percentages, units and euros. A single unit mistake (minutes read as hours, a 0–1 ratio read as a percentage) silently changes a € result by a factor of 60 or 100. CLAUDE.md requires units in every name, UTC storage and integer euro cents.

## Decision

**Unit suffixes** on every field and column that holds a quantity:

| Suffix | Meaning |
|---|---|
| `_s`, `_min`, `_h` | Duration in seconds, minutes, hours |
| `_pct` | Percentage, stored 0–100 (never 0–1) |
| `_units` | Count of product units |
| `_eur_cents` | Money, integer EUR cents |
| `_eur_cents_per_h` | Money rate per hour |
| `_at` | Timezone-aware UTC instant |

Good: `run_min_per_unit`, `load_pct`, `sales_price_eur_cents`, `due_at`.
Bad: `duration`, `load`, `price`, `due_date`.

**Money:** integer EUR cents in storage and in the engine. Conversion to euros happens only when the UI formats a value.

**Time:** every instant is timezone-aware UTC in storage and in the engine. Naive datetimes are rejected. `Plant.timezone_iana` (e.g. `Europe/Amsterdam`) is used only for display and for reading source files. Weeks are ISO weeks in plant local time.

## Consequences

- The schema validators enforce these rules; a field without a unit suffix fails review.
- Imports must convert source units and time zones explicitly in their mapping.
- Rounding to whole euros happens once, in the UI, so totals always add up.
