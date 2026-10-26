#!/usr/bin/env bash
# Start this workspace's own stack (database, redis, API, worker) and the web app on its own port.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
set -a; . ./.env; set +a

docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d db redis migrate api worker
echo "run: API http://localhost:$CIP_API_PORT  web http://localhost:$CIP_WEB_PORT"
exec pnpm --filter web exec next dev --port "$CIP_WEB_PORT"
