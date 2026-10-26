# ADR-0007: Roles and access

- **Status:** Proposed
- **Date:** 2026-10-15
- **CLAUDE.md reference:** Users, Hard constraints, Recommendations and AI (humans decide)

## Context

CLAUDE.md names five users (plant director, COO, planner, shift lead, IT). The mockup review added operators via a station screen and decided that the COO controls what each role can see, with everyone seeing everything by default. Hiding whole pages is rarely what matters; money, plants and decisions are.

## Decision

**Six roles, each with a start page and a default menu:**

| Role | Start page | Login |
|---|---|---|
| Plant director | Overview | Personal |
| COO | Overview (multi-plant overview later) | Personal |
| Planner | Planner today | Personal |
| Shift lead | Shift and floor (with TV mode) | Personal |
| Station (operators) | Station screen | Station PIN, belongs to the machine |
| IT / ERP owner | Connections | Personal |

**Access has three axes, set by the COO:**

1. **Pages:** which pages a role may open. Default: every role may open every page. Start pages are always allowed.
2. **Data:** money shown as € or as constraint hours only; all plants or own plant only. Default: € and all plants.
3. **Decisions:** who may act. Defaults:

| Decision | Default roles |
|---|---|
| Accept or reject Exploit and Subordinate actions | Director, COO, planner |
| Approve Elevate actions (they cost money) | Director, COO |
| Release and expedite orders | Planner, shift lead |
| Report a stop and its reason | Shift lead, station |
| Edit plant setup and capacity calendar | Planner, IT |
| Import data and run the diagnostic (upload, replace files, run) | Planner, IT |
| Fix rows in the app (and undo a fix) | Planner, IT |
| Delete an import | Planner, IT |
| Delete all data of a plant | IT |
| Sign off measured value | Director, COO |
| Manage logins | IT only |
| Change access | COO only |

The three import rights after the first were split off in CI0004 (ADR-0010) so the COO can, for example, leave fixing rows to IT only. A refused action names the roles that may do it now, and the page shows the same instead of the button.

**Separation:** the COO decides visibility and decisions; IT manages accounts. Every access and account change is audit-logged.

**Conversion to hours** for roles set to "hours only" is done by an engine function, never by the API or UI.

## Consequences

- Every endpoint checks page and decision rights; tests per role.
- The role switch in the header opens the chosen role's start page.
- Station screens never show who did what; they show what the station should do next.
