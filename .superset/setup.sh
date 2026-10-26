#!/usr/bin/env bash
# Workspace setup: .env with its own ports and Docker project, then dependencies.
# Safe to run again.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

slug="$(basename "$PWD" | tr -c 'a-zA-Z0-9\n' '-' | tr 'A-Z' 'a-z')"

# The main checkout keeps its own .env and the default ports; only linked worktrees get their own.
if [ "$(git rev-parse --git-dir)" = "$(git rev-parse --git-common-dir)" ]; then
  echo "setup: main checkout, .env left as it is"
  uv sync --frozen
  pnpm install --frozen-lockfile
  exit 0
fi

# 1. .env: copy from the main checkout (never committed), else from .env.example.
if [ ! -f .env ]; then
  for src in "${CIP_ENV_SOURCE:-}" "$HOME/Constraint_Intelligence_Platform/.env" \
             "$(git worktree list --porcelain | awk 'NR==1{print $2}')/.env" .env.example; do
    if [ -n "$src" ] && [ -f "$src" ]; then cp "$src" .env; echo "setup: .env from $src"; break; fi
  done
fi

# 2. Own ports and Docker project per workspace, so parallel workspaces never share a database.
port_free() { ! lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }
offset=$(( $(printf '%s' "$slug" | cksum | cut -d' ' -f1) % 300 + 1 ))
while ! { port_free $((55432 + offset)) && port_free $((56379 + offset)) \
          && port_free $((58000 + offset)) && port_free $((53000 + offset)); }; do
  offset=$(( offset % 300 + 1 ))
done

set_env() {
  if grep -q "^$1=" .env; then sed -i.bak "s|^$1=.*|$1=$2|" .env && rm -f .env.bak
  else echo "$1=$2" >> .env; fi
}
if ! grep -q '^CIP_WORKSPACE=' .env; then
  set_env COMPOSE_PROJECT_NAME "cip-$slug"
  set_env CIP_DB_PORT $((55432 + offset))
  set_env CIP_REDIS_PORT $((56379 + offset))
  set_env CIP_API_PORT $((58000 + offset))
  set_env CIP_WEB_PORT $((53000 + offset))
  set_env CIP_API_URL "http://localhost:$((58000 + offset))"
  set_env CIP_WORKSPACE "$slug"
fi
grep -E '^(COMPOSE_PROJECT_NAME|CIP_(DB|REDIS|API|WEB)_PORT)=' .env | sed 's/^/setup: /'

# 3. Dependencies.
uv sync --frozen
pnpm install --frozen-lockfile
echo "setup: done"
