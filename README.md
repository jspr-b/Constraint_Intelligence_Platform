# Constraint Intelligence Platform

A visual decision layer for manufacturing plants. It reads existing ERP, MES and machine data and shows what those systems do not: which resource limits output (the constraint), what that costs in euros, where the constraint will move in the coming weeks, and which Theory of Constraints actions recover the most. Every number is calculated and traceable to its inputs and formula.

- Product and engineering spec: [CLAUDE.md](CLAUDE.md)
- Data a plant needs to deliver: [docs/input-data.md](docs/input-data.md)
- Architecture decisions: [docs/adr/](docs/adr/README.md)

## Quickstart

Requirements: Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 24 with pnpm 10, Docker.

```bash
uv sync
pnpm install
uv run pre-commit install
```

## Commands

```bash
docker compose up              # full local stack
uv run pytest                  # Python tests
uv run ruff check . && uv run mypy .
pnpm --filter web dev          # frontend dev server
pnpm --filter web test         # frontend unit tests
pnpm --filter web e2e          # Playwright
uv run python -m constraint_engine.diagnose data/synthetic/plant_a  # offline diagnostic run
```

More:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up db redis migrate api worker  # hot reload
uv run python -m cip_api.bootstrap --tenant "Demo Metal (synthetic)" --it-email it@demo.example  # first IT account
pnpm --filter web e2e:live     # Playwright against the real stack (API, database, worker)
bash scripts/check-generated.sh  # OpenAPI, TS client, JSON Schema and onboarding docs up to date
pnpm onboarding:pdf            # prospect data checklist as PDF (EN/NL)
```

Local ports: web 53000, API 58000, Postgres 55432, Redis 56379. Sign-in and roles: [docs/auth.md](docs/auth.md). Onboarding a plant: [docs/onboarding/](docs/onboarding/).

## Licence

Not yet decided (open-core: the engine is an open-source candidate).
