#!/usr/bin/env bash
# Phase 8 SEC-06 + OPS-06 pre-publish gate.
# Runs all four audit scripts; fails fast on the first non-zero exit.
#
# Prerequisites (operator dev machine, before going public):
#   - gitleaks   (brew install gitleaks)
#   - exiftool   (brew install exiftool   /  sudo apt install -y libimage-exiftool-perl)
#   - node + npm (for `npm audit` against frontend/) — npm ships with Node
#   - uv         (for `uv run pip-audit` against Python deps)
#
# Operator must chmod +x on first checkout if not already executable:
#   chmod +x scripts/verify-phase8-audit.sh

set -euo pipefail

missing_prereqs=()
command -v exiftool >/dev/null 2>&1 || missing_prereqs+=("exiftool")
command -v gitleaks >/dev/null 2>&1 || missing_prereqs+=("gitleaks")
command -v npm >/dev/null 2>&1 || missing_prereqs+=("npm")
command -v uv >/dev/null 2>&1 || missing_prereqs+=("uv")

if [[ ${#missing_prereqs[@]} -gt 0 ]]; then
  echo "ERROR: missing prerequisite tools: ${missing_prereqs[*]}"
  echo "  macOS: brew install ${missing_prereqs[*]}"
  echo "  Debian/Pi: apt install -y libimage-exiftool-perl gitleaks nodejs npm"
  echo "  uv (any): curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 2
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "===== 1/5 gitignore completeness ====="
bash "$REPO_ROOT/scripts/audit-gitignore-completeness.sh"

echo ""
echo "===== 2/5 EXIF GPS sweep ====="
bash "$REPO_ROOT/scripts/audit-exif-gps.sh"

echo ""
echo "===== 3/5 gitleaks full-history ====="
bash "$REPO_ROOT/scripts/audit-gitleaks-history.sh"

echo ""
echo "===== 4/5 Python dependency vulnerabilities (pip-audit) ====="
# observatory itself isn't on PyPI; pip-audit reports it as skip — that's expected.
(cd "$REPO_ROOT" && uv run pip-audit 2>&1) | tee /tmp/pip-audit.log
if grep -qE "[1-9][0-9]* known vulnerab|Found" /tmp/pip-audit.log; then
  echo "FAIL: pip-audit reported vulnerabilities — see /tmp/pip-audit.log"
  exit 1
fi

echo ""
echo "===== 5/5 Frontend npm dependency vulnerabilities (npm audit, prod only) ====="
(cd "$REPO_ROOT/frontend" && npm audit --omit=dev) || {
  echo "FAIL: npm audit found vulnerabilities in frontend production deps"
  exit 1
}

echo ""
echo "PHASE 8 AUDIT: PASS (5/5 gates)"
