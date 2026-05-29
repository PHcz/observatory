#!/usr/bin/env bash
# Phase 8 SEC-06 + OPS-06 pre-publish gate.
# Runs all three audit scripts; fails fast on the first non-zero exit.
#
# Prerequisites (operator dev machine, before going public):
#   - gitleaks   (brew install gitleaks)
#   - exiftool   (brew install exiftool   /  sudo apt install -y libimage-exiftool-perl)
#
# Operator must chmod +x on first checkout if not already executable:
#   chmod +x scripts/verify-phase8-audit.sh

set -euo pipefail

missing_prereqs=()
command -v exiftool >/dev/null 2>&1 || missing_prereqs+=("exiftool")
command -v gitleaks >/dev/null 2>&1 || missing_prereqs+=("gitleaks")

if [[ ${#missing_prereqs[@]} -gt 0 ]]; then
  echo "ERROR: missing prerequisite tools: ${missing_prereqs[*]}"
  echo "  macOS: brew install ${missing_prereqs[*]}"
  echo "  Debian/Pi: apt install -y libimage-exiftool-perl gitleaks"
  exit 2
fi

echo "===== 1/3 gitignore completeness ====="
bash scripts/audit-gitignore-completeness.sh

echo ""
echo "===== 2/3 EXIF GPS sweep ====="
bash scripts/audit-exif-gps.sh

echo ""
echo "===== 3/3 gitleaks full-history ====="
bash scripts/audit-gitleaks-history.sh

echo ""
echo "PHASE 8 AUDIT: PASS"
