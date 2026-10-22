#!/usr/bin/env bash
# Print an id for the current source: the git tree of the working directory, including
# uncommitted and untracked (not ignored) files. Same files, same id.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
index="$(mktemp)"
trap 'rm -f "$index"' EXIT
cp "$(git rev-parse --git-path index)" "$index"
GIT_INDEX_FILE="$index" git add -A
GIT_INDEX_FILE="$index" git write-tree
