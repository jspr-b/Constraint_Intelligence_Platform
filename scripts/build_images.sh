#!/usr/bin/env bash
# Build every image (api, migrate, worker, web) stamped with the current source id.
# Extra arguments go to `docker compose build`, e.g. a service name.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
CIP_SOURCE_ID="$(bash scripts/source_id.sh)"
export CIP_SOURCE_ID
echo "Building images for source ${CIP_SOURCE_ID}"
docker compose build "$@"
