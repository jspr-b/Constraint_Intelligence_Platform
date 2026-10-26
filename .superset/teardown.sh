#!/usr/bin/env bash
# Remove this workspace's own containers and database. Only touches its own Docker project.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
project="$(grep '^COMPOSE_PROJECT_NAME=' .env 2>/dev/null | cut -d= -f2 || true)"
case "$project" in
  cip-*) docker compose -p "$project" down -v --remove-orphans || true ;;
  *) echo "teardown: no workspace Docker project in .env, nothing removed" ;;
esac
