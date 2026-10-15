# Architecture decision records

Every architecture decision is recorded here before it is implemented (CLAUDE.md, Code rules).

## Index

| # | Title | Status |
|---|---|---|
| [0001](0001-monorepo-and-stack.md) | Monorepo layout and stack choices | Proposed |
| [0002](0002-units-money-and-time.md) | Units, money and time | Proposed |
| [0003](0003-provenance-and-missing-data.md) | Provenance and missing data | Proposed |
| [0004](0004-tenancy.md) | Tenancy and deployment | Proposed |
| [0005](0005-privacy.md) | Privacy: no individual monitoring | Proposed |
| [0006](0006-frontend.md) | Frontend stack and theme | Proposed |
| [0007](0007-roles-and-access.md) | Roles and access | Proposed |
| [0008](0008-flow-views.md) | Plant flow views | Proposed |

## Adding an ADR

1. Copy [0000-template.md](0000-template.md) to `NNNN-short-title.md` with the next free number.
2. Fill in Context, Decision and Consequences, and name the CLAUDE.md section it implements.
3. Add a row to the index with status Proposed.
4. The user accepts it; then set the status to Accepted. A later decision that replaces it marks the old one "Superseded by ADR-NNNN".
