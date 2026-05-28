#!/usr/bin/env bash
# Phase 8 SEC-06 + OPS-06 pre-publish gate.
# Runs all three audit scripts; fails fast on the first non-zero exit.
#
# Operator must chmod +x on first checkout if not already executable:
#   chmod +x scripts/verify-phase8-audit.sh
set -euo pipefail
bash scripts/audit-gitignore-completeness.sh
bash scripts/audit-exif-gps.sh
bash scripts/audit-gitleaks-history.sh
echo "PHASE 8 AUDIT: PASS"
