#!/usr/bin/env bash
# Fail when a running container was built from other code than the working directory, or runs
# an older image than the one now tagged. Run after `docker compose up -d --no-build`.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
want="$(bash scripts/source_id.sh)"
fail=0
for service in api worker web; do
  container="$(docker compose ps -q "$service")"
  if [ -z "$container" ]; then
    echo "FAIL $service: not running (docker compose up -d --no-build)"; fail=1; continue
  fi
  running_image="$(docker inspect -f '{{.Image}}' "$container")"
  tagged_image="$(docker image inspect -f '{{.Id}}' "$(docker inspect -f '{{.Config.Image}}' "$container")" 2>/dev/null || true)"
  built_from="$(docker image inspect -f '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$running_image" 2>/dev/null || true)"
  if [ "$running_image" != "$tagged_image" ]; then
    echo "FAIL $service: runs an older image than the tagged one (docker compose up -d --no-build)"; fail=1
  elif [ "$built_from" != "$want" ]; then
    echo "FAIL $service: built from ${built_from:-unknown}, source is $want (bash scripts/build_images.sh)"; fail=1
  else
    echo "ok   $service: built from the current source"
  fi
done
exit "$fail"
