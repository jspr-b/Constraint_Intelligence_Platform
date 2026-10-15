# ADR-0001: Monorepo layout and stack choices

- **Status:** Proposed
- **Date:** 2026-10-15
- **CLAUDE.md reference:** Repository structure, Tech stack, Dev stack

## Context

CLAUDE.md fixes the repository layout and most of the stack, but leaves some choices open: pandas or Polars, Celery or Dramatiq, Keycloak or Auth0. Every later sequence needs these settled, and the Python packages need import names.

## Decision

**Layout** follows CLAUDE.md "Repository structure". Python import names:

| Directory | Import name | Role |
|---|---|---|
| `packages/schema` | `cip_schema` | Standard production-flow data model |
| `packages/constraint_engine` | `constraint_engine` | All calculations; open-source candidate |
| `packages/connectors` | `cip_connectors` | ERP/MES/file adapters → standard schema |
| `apps/api` | `cip_api` | FastAPI service |
| `workers` | `cip_workers` | Background jobs |

`apps/web` (Next.js) and `packages/ui` (components and tokens) are pnpm workspace members.

**Versions:** Python 3.12, Node 24, pnpm 10. Python packages form one uv workspace; JS packages one pnpm workspace.

**Open choices settled:**

- **Polars** is the engine's dataframe library. pandas only at I/O edges where a library requires it. Reason: faster on event logs with millions of rows, strict types, and runs the same on a laptop and on data platforms.
- **Dramatiq + Redis** for background jobs. Reason: smaller and simpler than Celery for our job types (import, reconstruction, detection runs).
- **Auth provider is deferred** to the login sequence (ADR-0007 covers roles). The auth layer is OIDC-ready; Microsoft Entra ID is configuration, so the choice between Keycloak and Auth0 does not block the foundation.
- **Synthetic plant generation lives in `constraint_engine.synthetic`**, because public benchmark datasets are part of the open core.

## Consequences

- Every later task uses these names; renaming later means touching all packages.
- Polars-first means engine functions take and return Polars frames; adapters convert at the edges.
- The auth provider decision stays open until a pilot plant's IT requirements are known.
