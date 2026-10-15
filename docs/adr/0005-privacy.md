# ADR-0005: Privacy: no individual monitoring

- **Status:** Proposed
- **Date:** 2026-10-15
- **CLAUDE.md reference:** Hard constraints (no individual employee monitoring), Key risks (floor resistance to monitoring)

## Context

Measuring task times on the floor can easily turn into measuring people. Under GDPR (AVG) and article 27 of the Dutch Works Councils Act, performance monitoring of employees needs works council consent. Beyond the law, floor resistance would kill adoption.

## Decision

- **Measure resources, operations, tasks and stations. Never named people.**
- **No person-identifying field on floor data.** The schema has no operator, employee, worker, badge or person field on events, orders or machines. A schema test walks every model and fails on a denylist of field names (operator, employee, worker, person, badge, first_name, last_name, email, phone, user_id).
- **Personal columns are dropped on import** before any row is parsed; their values never reach storage, logs or error messages.
- **Station logins belong to a machine**, not a person.
- **Personal accounts** exist only for people who plan, decide or administer (planner, director, COO, shift lead, IT). Their activity in the app may be audit-logged (who changed access, who accepted an action), but nothing measures how fast or how much they work.
- **Logs never contain plant data values**, only ids, counts and timings.

## Consequences

- Task times can be shown per operation and station without consent issues.
- Some customers will ask for per-person metrics; the answer is no, and the product says why.
- The import must recognise personal columns in unknown exports; the mapping marks them, and the denylist catches common names.
