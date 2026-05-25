#!/usr/bin/env bash
# Re-capture Phase 5 pinned fixtures from NOAA SWPC and AuroraWatch UK.
# Run manually when an upstream format changes (parser test fails) or to refresh.
# NEVER auto-run in CI — fixtures are pinned for reproducibility.
#
# Blitzortung fixture is captured separately by Plan 05-04 once the WS port probe
# succeeds (it's a WebSocket stream, not a curl-able endpoint).
#
# Recapture procedure: bash scripts/capture-phase5-fixtures.sh
# Commit with: chore(05-XX): refresh phase 5 fixtures (YYYY-MM-DD)

set -euo pipefail

UA="observatory/0.1 (https://github.com/PHcz/observatory)"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FX="$ROOT/tests/fixtures"
mkdir -p "$FX/noaa" "$FX/aurora" "$FX/blitzortung"

echo "NOAA Kp 1-min..."
curl -fsSL -H "User-Agent: $UA" \
  "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json" \
  -o "$FX/noaa/kp_sample.json"

echo "NOAA solar wind plasma 2h..."
curl -fsSL -H "User-Agent: $UA" \
  "https://services.swpc.noaa.gov/products/solar-wind/plasma-2-hour.json" \
  -o "$FX/noaa/solar_wind_sample.json"

echo "NOAA GOES X-ray 6h..."
curl -fsSL -H "User-Agent: $UA" \
  "https://services.swpc.noaa.gov/json/goes/primary/xrays-6-hour.json" \
  -o "$FX/noaa/xray_sample.json"

echo "AuroraWatch UK current status..."
curl -fsSL -H "User-Agent: $UA" \
  "https://aurorawatch-api.lancs.ac.uk/0.2/status/current-status.xml" \
  -o "$FX/aurora/current_status_sample.xml"

echo
echo "NOAA + AuroraWatch fixtures refreshed at $(date -u +%FT%TZ)"
echo "Blitzortung fixture must be captured by 05-04 (WebSocket; not a curl)"
echo
echo "Sizes:"
wc -c \
  "$FX/noaa/kp_sample.json" \
  "$FX/noaa/solar_wind_sample.json" \
  "$FX/noaa/xray_sample.json" \
  "$FX/aurora/current_status_sample.xml"
