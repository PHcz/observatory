#!/usr/bin/env bash
# Pre-publish full-history secrets scan. Run from repo root.
# Exits non-zero on any finding.
#
# Operator must chmod +x on first checkout if not already executable:
#   chmod +x scripts/audit-gitleaks-history.sh
set -euo pipefail
gitleaks detect \
  --source . \
  --config .gitleaks.toml \
  --log-opts="--all --full-history" \
  --report-format=json \
  --report-path=.planning/phases/08-dashboard-polish-security-audit-7-day-test/08-GITLEAKS-AUDIT.json \
  --redact
