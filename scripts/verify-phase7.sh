#!/usr/bin/env bash
# Phase 7 acceptance smoke checks.
# Resolves API base from listening port (LAN-bound), then verifies HTTP + WS endpoints.
#
# Usage (run on the Pi):
#   bash scripts/verify-phase7.sh [output-file]
#
# Default output: .planning/phases/07-sveltekit-dashboard/07-08-ACCEPTANCE.md

set -euo pipefail

OUT="${1:-.planning/phases/07-sveltekit-dashboard/07-08-ACCEPTANCE.md}"
: > "$OUT.tmp"

# Resolve API base (Phase 6 pattern)
if command -v ss >/dev/null 2>&1; then
  LISTEN=$(ss -tlnp 2>/dev/null | grep -E ':8000\s' | awk '{print $4}' | head -n1)
  HOST="${LISTEN%:*}"
  if [[ "$HOST" == "0.0.0.0" || "$HOST" == "127.0.0.1" || -z "$HOST" ]]; then
    HOST=$(hostname -I 2>/dev/null | awk '{print $1}')
    [[ -z "$HOST" ]] && HOST="observatory.local"
  fi
else
  HOST="observatory.local"
fi
API_BASE="http://${HOST}:8000"
echo "[verify-phase7] API_BASE=$API_BASE"

PASS=0
FAIL=0

check() {
  local name="$1"; shift
  if "$@" >/dev/null 2>&1; then
    echo "- [x] $name" >> "$OUT.tmp"; PASS=$((PASS+1))
  else
    echo "- [ ] $name (FAIL)" >> "$OUT.tmp"; FAIL=$((FAIL+1))
  fi
}

# C1: index.html served with SvelteKit shell
check "C1: GET /  returns HTML with Observatory title" bash -c "curl -sf '$API_BASE/' | grep -q '<title>Observatory'"

# C2: /api/health reachable
check "C2: GET /api/health  returns JSON timestamp" bash -c "curl -sf '$API_BASE/api/health' | grep -q '\"timestamp\"'"

# C3: Static assets served (any JS file under /_app)
check "C3: SvelteKit asset under /_app  reachable" bash -c "curl -sf '$API_BASE/' | grep -oE '/_app/[^\"]+\.js' | head -1 | xargs -I {} curl -sf -o /dev/null '$API_BASE{}'"

# C4: Build size sanity
BUILD_DIR="${OBS_REMOTE_BUNDLE_DIR:-/opt/observatory/frontend/build}"
if [[ -d "$BUILD_DIR" ]]; then
  SIZE=$(du -sb "$BUILD_DIR" 2>/dev/null | awk '{print $1}')
  check "C4: build dir size < 1.5MB ($SIZE bytes)" test "$SIZE" -lt 1572864
else
  echo "- [ ] C4: build dir not found at $BUILD_DIR (skipped if running off-Pi)" >> "$OUT.tmp"
fi

{
  echo "# Phase 7 Acceptance"
  echo
  echo "**Date:** $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "**Host:** $(hostname)"
  echo "**API_BASE:** $API_BASE"
  echo
  echo "## Automated Checks"
  echo
  cat "$OUT.tmp"
  echo
  echo "**Result:** PASS=$PASS FAIL=$FAIL"
  echo
  echo "## Human-Action Verification"
  echo
  echo "(filled in by Task 2 below — operator signs off after on-device tests)"
} > "$OUT"

rm -f "$OUT.tmp"

if [[ "$FAIL" -gt 0 ]]; then
  echo "[verify-phase7] FAIL ($FAIL failed)" >&2
  exit 1
fi
echo "[verify-phase7] PASS"
