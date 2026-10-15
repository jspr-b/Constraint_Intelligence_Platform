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

Some commands become available as the foundation festival progresses (Docker Compose, the web app, the diagnose CLI).

## Licence

Not yet decided (open-core: the engine is an open-source candidate).
