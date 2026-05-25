#!/usr/bin/env bash
# Re-capture pinned fixtures from all three earthquake sources.
# Run manually when an upstream format changes (parser test fails).
# NEVER auto-run in CI — fixtures are pinned for reproducibility.
set -euo pipefail
UA="observatory/0.1 (https://github.com/PHcz/observatory)"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FX="$ROOT/tests/fixtures/earthquakes"
mkdir -p "$FX/usgs" "$FX/emsc" "$FX/bgs"
echo "USGS..."
curl -sSfL -A "$UA" \
  "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson" \
  -o "$FX/usgs/sample_4_5_day.json"
echo "EMSC..."
curl -sSfL -A "$UA" \
  "https://www.seismicportal.eu/fdsnws/event/1/query?format=json&limit=200&minmag=2.5" \
  -o "$FX/emsc/sample_pastday.json"
echo "BGS..."
curl -sSfL -A "$UA" \
  "http://earthquakes.bgs.ac.uk/feeds/MhSeismology.xml" \
  -o "$FX/bgs/sample_recent.xml"
echo "Captured. Review sizes:"
wc -c "$FX/usgs/sample_4_5_day.json" "$FX/emsc/sample_pastday.json" "$FX/bgs/sample_recent.xml"
