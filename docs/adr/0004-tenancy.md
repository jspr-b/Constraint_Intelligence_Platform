# ADR-0004: Tenancy and deployment

- **Status:** Proposed
- **Date:** 2026-10-15
- **CLAUDE.md reference:** Hard constraints (plant data is confidential), Deployment

## Context

Plant data is confidential and customers compete with each other. The platform runs multi-tenant in the cloud by default, but defence and regulated customers need on-premise. Data must stay in the EU.

## Decision

- **One database, strict row-level isolation.** Every table has `tenant_id NOT NULL`. Postgres row-level security is enabled on every table with the policy `tenant_id = current_setting('app.tenant_id')::uuid`.
- **The app connects as a non-superuser role** (`cip_app`) that does not own the tables, so row-level security cannot be bypassed. Migrations run as a separate owner role.
- **Every request sets the tenant** with `SET LOCAL app.tenant_id` inside its transaction. With no tenant set, queries return no rows.
- **Tenant comes from the session.** Until login exists, a dev-only `X-Tenant-Id` header is accepted when `CIP_ENV=dev`; in any other environment it is rejected.
- **Same container images for cloud and on-premise.** EU region for the hosted service (Azure West Europe or AWS eu-central-1).
- **Encryption** at rest (database and object storage) and in transit (TLS everywhere).

## Consequences

- A test proves isolation for every table, running as `cip_app`.
- Cross-tenant features (benchmarks, multi-plant for a group) need an explicit design later; they are not possible by accident.
- On-premise installs need no code changes, only configuration.
