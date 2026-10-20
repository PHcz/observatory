#!/usr/bin/env bash
# Deploy frontend/build/ to the Pi via rsync.
# Run from a Mac after `cd frontend && npm run build`.
#
# Refuses to run on the Pi itself (Linux + USER=observatory) — building on
# the Pi is explicitly out of scope per CLAUDE.md (no Node on the Pi).
#
# Deploys as root (--rsync-path="sudo rsync") then chowns to root:root -- the
# service account must not be able to rewrite what it serves (audit M8). A
# plain rsync as `ph` into a tree it does not own only
# writes the top-level files it can (200.html) and PARTIALLY FAILS on the
# subdirs (rsync exit 23) — leaving stale JS chunk hashes that the fresh
# index.html no longer references. The browser then gets the SPA HTML
# fallback for a missing .js and the app never hydrates (blank page).
# Deploying as root avoids the permission split entirely.

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
# Root rsync --delete + chown -R go into this path: only a directory strictly
# inside /opt/observatory, no "..", is acceptable (security audit F51).
if [[ ! "$REMOTE_DIR" =~ ^/opt/observatory/[A-Za-z0-9._/-]+$ ]] || [[ "$REMOTE_DIR" == *..* ]]; then
  echo "[deploy-frontend] refusing unsafe OBS_REMOTE_BUNDLE_DIR: '$REMOTE_DIR'" >&2
  exit 2
fi
REMOTE_HOST="${OBS_HTTP_HOST:-observatory.local}"

echo "[deploy-frontend] Rsyncing $BUILD_DIR/ -> $SSH_TARGET:$REMOTE_DIR/ (as root)"
# --rsync-path="sudo rsync": write as root so observatory-owned, non-group-
# writable subdirs (_app/immutable/*) sync completely. --delete removes stale
# chunk hashes so the served index never references a missing asset.
rsync -az --delete \
  --exclude='.svelte-kit' \
  --rsync-path="sudo rsync" \
  "$BUILD_DIR/" \
  "$SSH_TARGET:$REMOTE_DIR/"

echo "[deploy-frontend] Setting ownership to root:root"
ssh "$SSH_TARGET" "sudo chown -R root:root '$REMOTE_DIR'"

# Verify the deploy actually serves JS — a partial/failed sync makes the
# served index reference a .js the bundle dir lacks, and the SPA 404 fallback
# returns 200.html (text/html) for it, silently breaking hydration. Fail loud.
echo "[deploy-frontend] Verifying served assets..."
BASE="http://${REMOTE_HOST}:8000"
ENTRY=$(curl -fsS --max-time 10 "$BASE/" | grep -oE '/_app/immutable/entry/start\.[A-Za-z0-9_-]+\.js' | head -1 || true)
if [[ -z "$ENTRY" ]]; then
  echo "[deploy-frontend] WARNING: could not find the entry chunk in the served index — verify manually." >&2
  exit 0
fi
CT=$(curl -fsS -I --max-time 10 "$BASE$ENTRY" | grep -i '^content-type' | tr -d '\r')
case "$CT" in
  *javascript*)
    echo "[deploy-frontend] OK — $ENTRY served as JavaScript ($CT)."
    echo "[deploy-frontend] Done. Open http://${REMOTE_HOST}:8000/"
    ;;
  *)
    echo "[deploy-frontend] ERROR: $ENTRY served as '$CT' (expected JavaScript)." >&2
    echo "[deploy-frontend] The bundle is missing that chunk — the deploy did not fully sync." >&2
    exit 3
    ;;
esac
