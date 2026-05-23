#!/usr/bin/env bash
# Apply migrations/0001_initial_schema.sql to a temp DB and verify all 6 tables + indexes exist.
# Used by acceptance verification.
set -euo pipefail

TMPDB="$(mktemp -t observatory-schema.XXXXXX.db)"
trap 'rm -f "$TMPDB"' EXIT

sqlite3 "$TMPDB" < migrations/0001_initial_schema.sql

TABLES="$(sqlite3 "$TMPDB" "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")"
EXPECTED=$'aurora_status\nearthquakes\nlightning_strikes\nmuon_events\nspace_weather\nweather'
if [ "$TABLES" != "$EXPECTED" ]; then
  echo "FAIL: tables mismatch"
  echo "got:"
  echo "$TABLES"
  echo "want:"
  echo "$EXPECTED"
  exit 1
fi

INDEXES="$(sqlite3 "$TMPDB" "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%' ORDER BY name")"
EXPECTED_IDX=$'idx_aurora_ts\nidx_lightning_ts\nidx_muon_ts\nidx_quakes_mag\nidx_quakes_ts\nidx_sw_ts\nidx_weather_ts'
if [ "$INDEXES" != "$EXPECTED_IDX" ]; then
  echo "FAIL: indexes mismatch"
  echo "got:"
  echo "$INDEXES"
  echo "want:"
  echo "$EXPECTED_IDX"
  exit 1
fi

echo "OK: 6 tables, 7 indexes"
