#!/usr/bin/env bash
# UI-15 panel-siblings token audit. Greps each component CSS for `token:`
# annotation comments documented in
# .planning/phases/07-sveltekit-dashboard/07-UI-SPEC.md §"Panel-Siblings
# Spacing Tokens". Exit 0 — informational report.
#
# Note: StatsRow.svelte's token-annotation is applied by Phase 8 Plan 08-02
# Task 2 (delegated to eliminate a wave-2 stash/restore collision with 08-04).
# This script greps all 9 panels uniformly.
#
# Panels live in frontend/src/lib/panels/ (not /components/ — Phase 7 reshuffle).
#
# Sandbox note: pre-commit may block `chmod +x` on first checkout; run
# `bash scripts/audit-panel-tokens.sh` if not executable.
set -uo pipefail

COMPONENTS=(
  HeaderPanel StatsRow MuonChart TemperatureChart SpaceWeatherPanel
  EarthquakeList LightningPanel AuroraPanel HealthRow
)
PASS=0
FAIL=0

echo "UI-15 Panel Token Audit (token-vs-CSS)"
echo "======================================"

for c in "${COMPONENTS[@]}"; do
  f="frontend/src/lib/panels/${c}.svelte"
  if [[ ! -f "$f" ]]; then
    echo "MISS  $c — file not found at $f"
    FAIL=$((FAIL+1))
    continue
  fi
  # Each panel must carry at least one `token:` annotation comment
  if grep -q "token:" "$f"; then
    count=$(grep -c "token:" "$f")
    echo "PASS  $c — ${count} token annotation(s)"
    PASS=$((PASS+1))
  else
    echo "FAIL  $c — no \`token:\` comments found"
    FAIL=$((FAIL+1))
  fi
done

echo "--------------------------------------"
echo "Total: $((PASS+FAIL)) panels   PASS=$PASS   FAIL=$FAIL"

# Informational exit 0 — manual visual diff is the final authority per
# 08-VALIDATION.md §Manual-Only.
exit 0
