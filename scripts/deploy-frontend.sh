#!/usr/bin/env bash
# Deploy frontend/build/ to the Pi via rsync.
# Run from a Mac after `cd frontend && npm run build`.
#
# Refuses to run on the Pi itself (Linux + USER=observatory) — building on
# the Pi is explicitly out of scope per CLAUDE.md (no Node on the Pi).

set -euo pipefail

if [[ "$(uname -s)" == "Linux" ]] && [[ "${USER:-}" == "observatory" ]]; then
  echo "ERROR: refusing to run on the Pi (Linux + USER=observatory)." >&2
  echo "Build the frontend on a Mac and rsync from there." >&2
  exit 2
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_DIR="$REPO_ROOT/frontend/build"

if [[ ! -d "$BUILD_DIR" ]]; then
  echo "ERROR: $BUILD_DIR does not exist. Run 'cd frontend && npm run build' first." >&2
  exit 1
fi

SSH_TARGET="${OBS_SSH_TARGET:-ph@observatory.local}"
REMOTE_DIR="${OBS_REMOTE_BUNDLE_DIR:-/opt/observatory/frontend/build}"

echo "[deploy-frontend] Rsyncing $BUILD_DIR/ -> $SSH_TARGET:$REMOTE_DIR/"
rsync -avz --delete \
  --exclude='.svelte-kit' \
  "$BUILD_DIR/" \
  "$SSH_TARGET:$REMOTE_DIR/"

echo "[deploy-frontend] Done. Verify: curl http://observatory.local:8000/"
