#!/usr/bin/env bash
# Fails when generated files are stale: OpenAPI contract, TypeScript client types, JSON Schema.
set -euo pipefail
cd "$(dirname "$0")/.."
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

uv run python -m cip_api.export_openapi "$tmp/openapi.json" >/dev/null
diff -q apps/api/openapi.json "$tmp/openapi.json" >/dev/null \
  || { echo "apps/api/openapi.json is stale: run uv run python -m cip_api.export_openapi"; exit 1; }

pnpm --filter web exec openapi-typescript ../api/openapi.json -o "$tmp/schema.d.ts" >/dev/null 2>&1
diff -q apps/web/src/lib/api/schema.d.ts "$tmp/schema.d.ts" >/dev/null \
  || { echo "apps/web/src/lib/api/schema.d.ts is stale: run pnpm --filter web gen:api"; exit 1; }

echo "generated files are up to date"
