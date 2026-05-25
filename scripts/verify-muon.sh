#!/usr/bin/env bash
# On-Pi acceptance runner for Phase 2 muon detector.
#
# Verifies the four ROADMAP Phase 2 success criteria end-to-end:
#   1. muon_events rows advance continuously (>=10 new rows in 120s + MAX(ts) advances)
#   2. Unplug/replug PicoMuon USB cable -> service reconnects within 30s
#   3. 60s of simulated serial silence -> reader logs reopen warning,
#      systemd watchdog stays satisfied, service still active
#   4. Each recent muon_events row has detector_pressure_hpa + detector_temp_c
#      populated from the onboard BMP280
#
# Run on the Pi (NOT the dev Mac) as the `ph` login user:
#   cd /opt/observatory
#   bash scripts/verify-muon.sh
#
# The script will use sudo as needed (systemctl, chmod on /dev/ttyACM*).
# It is idempotent — re-runnable after a failure. It writes a sign-off
# record to .planning/phases/02-muon-detector/02-07-ACCEPTANCE.md (or
# /tmp/02-07-ACCEPTANCE.md if the repo path is read-only on the Pi).
#
# Pitfall 6 (per 02-CONTEXT.md): the muon service holds /dev/picomuon with
# exclusive=True. This script must NEVER open /dev/picomuon itself.
# For Criterion 3 we revoke read permission on the underlying ttyACM* node
# (the symlink target) so the reader's reopen attempts fail with EACCES —
# this exercises the same code path as a USB unplug from the reader's
# perspective, without us ever opening the port.
set -euo pipefail

# --- Config ---
DB="${OBSERVATORY_DB:-/var/lib/observatory/observatory.db}"
UNIT="obs-muon.service"
UNIT_PATH="/etc/systemd/system/${UNIT}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ACC_PRIMARY="${REPO_ROOT}/.planning/phases/02-muon-detector/02-07-ACCEPTANCE.md"
ACC_FALLBACK="/tmp/02-07-ACCEPTANCE.md"
TS_NOW="$(date -Iseconds)"
OPERATOR="${SUDO_USER:-${USER:-unknown}}"
HOSTNAME_S="$(hostname)"

# --- Colour helpers ---
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
pass(){ echo -e "${GREEN}[PASS]${NC} $*"; }
fail(){ echo -e "${RED}[FAIL]${NC} $*"; FAILED=1; }
warn(){ echo -e "${YELLOW}[WARN]${NC} $*"; }
info(){ echo -e "${BLUE}[INFO]${NC} $*"; }
hdr(){  echo ""; echo -e "${BLUE}=== $* ===${NC}"; }

FAILED=0
declare -A RESULTS
RESULTS[1]="NOT RUN"
RESULTS[2]="NOT RUN"
RESULTS[3]="NOT RUN"
RESULTS[4]="NOT RUN"

# Anomalies (free-form notes appended to ACCEPTANCE.md)
ANOMALIES=()

# --- Pick output path for ACCEPTANCE.md ---
ACC="$ACC_PRIMARY"
ACC_DIR="$(dirname "$ACC")"
if [ ! -d "$ACC_DIR" ] || [ ! -w "$ACC_DIR" ]; then
  warn "Cannot write to ${ACC_DIR}; falling back to ${ACC_FALLBACK}"
  ACC="$ACC_FALLBACK"
fi

# --- Precondition: required binaries ---
hdr "Precondition: required binaries"
for bin in sqlite3 systemctl systemd-analyze chronyc readlink stat journalctl awk sudo; do
  if ! command -v "$bin" >/dev/null 2>&1; then
    fail "missing required binary: ${bin}"
    exit 1
  fi
done
pass "all required binaries present"

# --- Precondition: unit file installed + lints clean ---
hdr "Precondition: systemd-analyze verify ${UNIT}"
if [ ! -f "$UNIT_PATH" ]; then
  fail "${UNIT_PATH} not found — run bootstrap-pi.sh on the Pi first (or cp + daemon-reload)"
  exit 1
fi
if systemd-analyze verify "$UNIT_PATH" 2>&1; then
  pass "unit lints clean"
else
  fail "unit lints with errors — aborting"
  exit 1
fi

# --- Precondition: /dev/picomuon symlink exists ---
hdr "Precondition: /dev/picomuon symlink"
if [ ! -e /dev/picomuon ]; then
  fail "/dev/picomuon symlink missing — udev rule not loaded or PicoMuon not plugged in"
  exit 1
fi
DEV_TARGET="$(readlink -f /dev/picomuon)"
info "symlink resolves to ${DEV_TARGET}"

# --- Precondition: chrony offset ---
hdr "Precondition: chronyc tracking"
OFFSET="$(chronyc tracking | awk -F: '/^System time/ {print $2}' | awk '{print $1}')"
if [ -z "$OFFSET" ]; then
  warn "could not parse chronyc tracking output; continuing"
  OFFSET="unknown"
else
  info "chrony offset at start: ${OFFSET}s"
fi

# --- Make sure the service is running ---
hdr "Starting ${UNIT} (if not already running)"
sudo systemctl start "$UNIT"
sleep 3
STATE_PRE="$(systemctl is-active "$UNIT" || true)"
if [ "$STATE_PRE" != "active" ]; then
  fail "${UNIT} failed to start (state=${STATE_PRE}) — check journalctl -u ${UNIT}"
  sudo journalctl -u "$UNIT" -n 30 --no-pager
  exit 1
fi
pass "${UNIT} is active"
N_RESTARTS_START="$(systemctl show -p NRestarts --value "$UNIT")"
info "NRestarts at start: ${N_RESTARTS_START}"

# Give the NTP gate + first reads a moment to complete
sleep 5

# ========================================================================
# Criterion 1: row growth over 2 minutes
# ========================================================================
hdr "Criterion 1: muon_events row growth (waiting 120s)"
START_COUNT="$(sqlite3 "$DB" 'SELECT COUNT(*) FROM muon_events;')"
START_MAX="$(sqlite3 "$DB" 'SELECT COALESCE(MAX(ts),0) FROM muon_events;')"
info "start: count=${START_COUNT} max_ts=${START_MAX}"
sleep 120
END_COUNT="$(sqlite3 "$DB" 'SELECT COUNT(*) FROM muon_events;')"
END_MAX="$(sqlite3 "$DB" 'SELECT COALESCE(MAX(ts),0) FROM muon_events;')"
DELTA=$((END_COUNT - START_COUNT))
info "end:   count=${END_COUNT} max_ts=${END_MAX} delta=${DELTA}"

# Threshold: 10 events in 120s is well below the 175 events/min observed on real
# hardware (02-01-CAPTURE-NOTES.md) but high enough to fail on a stuck pipeline.
if [ "$DELTA" -ge 10 ] && [ "$END_MAX" -gt "$START_MAX" ]; then
  pass "Criterion 1: ${DELTA} new events in 120s; MAX(ts) advanced (${START_MAX} -> ${END_MAX})"
  RESULTS[1]="PASS (delta=${DELTA}, max_ts ${START_MAX} -> ${END_MAX})"
else
  fail "Criterion 1: only ${DELTA} new events in 120s (expected >=10); max_ts ${START_MAX} -> ${END_MAX}"
  RESULTS[1]="FAIL (delta=${DELTA}, max_ts ${START_MAX} -> ${END_MAX})"
  ANOMALIES+=("Criterion 1: ingest rate below 10/120s — check journalctl -u ${UNIT} for parse_error or open errors.")
fi

# ========================================================================
# Criterion 2: unplug/replug recovers within 30s
# ========================================================================
hdr "Criterion 2: unplug/replug (interactive)"
echo "Now physically unplug the PicoMuon USB cable from the Pi."
read -r -p "Press ENTER once the cable is unplugged..." _
UNPLUG_TS=$(date +%s)
info "unplug recorded at $(date -d @${UNPLUG_TS} -Iseconds 2>/dev/null || date -Iseconds)"
sleep 5  # let kernel notice the disconnect

echo ""
echo "Now plug the PicoMuon USB cable back in."
read -r -p "Press ENTER once the cable is re-plugged..." _
REPLUG_TS=$(date +%s)
info "replug recorded at $(date -d @${REPLUG_TS} -Iseconds 2>/dev/null || date -Iseconds)"

# Reader needs a moment + udev needs to re-create /dev/picomuon
BASELINE_COUNT="$(sqlite3 "$DB" 'SELECT COUNT(*) FROM muon_events;')"
info "baseline count after replug: ${BASELINE_COUNT}; watching for new rows for up to 30s..."

# Worst-case backoff before replug is 1+2+5+10 = 18s (per 02-05 BACKOFF_SEQUENCE_SEC),
# so 30s gives ~12s headroom for the actual replug to settle.
DEADLINE=$(( REPLUG_TS + 30 ))
RECOVERED=0
while [ "$(date +%s)" -lt "$DEADLINE" ]; do
  NOW_COUNT="$(sqlite3 "$DB" 'SELECT COUNT(*) FROM muon_events;')"
  if [ "$NOW_COUNT" -gt "$BASELINE_COUNT" ]; then
    ELAPSED=$(( $(date +%s) - REPLUG_TS ))
    pass "Criterion 2: rows resumed ${ELAPSED}s after replug (count ${BASELINE_COUNT} -> ${NOW_COUNT})"
    RESULTS[2]="PASS (recovered in ${ELAPSED}s; count ${BASELINE_COUNT} -> ${NOW_COUNT})"
    RECOVERED=1
    break
  fi
  sleep 2
done
if [ "$RECOVERED" -eq 0 ]; then
  fail "Criterion 2: no new rows within 30s of replug"
  RESULTS[2]="FAIL (no new rows within 30s of replug)"
  ANOMALIES+=("Criterion 2: no row growth within 30s of replug — check that /dev/picomuon symlink reappeared (udev rule serial-anchor variant may be required).")
fi

# Refresh DEV_TARGET — after a replug, the underlying ttyACM* number may have
# changed (e.g. ttyACM0 -> ttyACM1). The symlink follows it.
if [ -e /dev/picomuon ]; then
  DEV_TARGET="$(readlink -f /dev/picomuon)"
  info "after replug, /dev/picomuon resolves to ${DEV_TARGET}"
else
  warn "/dev/picomuon symlink missing after replug — udev rule may need a re-trigger"
fi

# ========================================================================
# Criterion 3: 60s silence triggers warning + watchdog stays satisfied
# ========================================================================
hdr "Criterion 3: simulated serial silence (90s)"

# Pitfall 6: do NOT open /dev/picomuon. Revoke read perm on the underlying
# ttyACM* node so the reader's reopen attempts get EACCES. We chmod the
# resolved target (NOT the symlink — chmod on a symlink targets the link itself
# on Linux, but stat -c %a follows it).
if [ ! -e "$DEV_TARGET" ]; then
  warn "Skipping Criterion 3: ${DEV_TARGET} no longer exists"
  RESULTS[3]="SKIP (DEV_TARGET missing)"
  ANOMALIES+=("Criterion 3 skipped: ${DEV_TARGET} not present at start of silence test.")
else
  ORIG_MODE="$(stat -c %a "$DEV_TARGET")"
  LOG_START_TS="$(date -Iseconds)"
  info "blocking access to ${DEV_TARGET} (was mode ${ORIG_MODE}); reader should hit EACCES on next reopen"
  sudo chmod 000 "$DEV_TARGET"
  # 70s ensures we cross the 60s silence_timeout_sec threshold in reader.py
  # AND we observe at least one reopen attempt being denied.
  info "sleeping 70s with port blocked..."
  sleep 70
  info "restoring mode ${ORIG_MODE} on ${DEV_TARGET}"
  sudo chmod "$ORIG_MODE" "$DEV_TARGET"
  # Reader needs time to next reopen attempt (up to 30s in backoff schedule) +
  # NTP gate (in-process is not re-run on reopen, only on full systemd restart).
  info "sleeping 30s for reader recovery..."
  sleep 30

  # 3a: WARNING log present mentioning silence/reopen/serial_error
  SILENCE_LOG="$(sudo journalctl -u "$UNIT" --since "$LOG_START_TS" --no-pager 2>&1 || true)"
  if echo "$SILENCE_LOG" | grep -qE 'serial_silence_reopen|reopen_attempt|serial_error|reopening_after_silence'; then
    pass "Criterion 3a: reader logged silence/reopen warning during blockade"
    LOG_RESULT_3A="PASS"
  else
    fail "Criterion 3a: no silence/reopen warning in journal during blockade"
    LOG_RESULT_3A="FAIL"
    echo "--- last 20 lines of journal during blockade ---"
    echo "$SILENCE_LOG" | tail -20
    echo "--- end ---"
    ANOMALIES+=("Criterion 3a: expected one of [serial_silence_reopen, reopen_attempt, serial_error, reopening_after_silence] in journalctl since blockade start; none found.")
  fi

  # 3b: service is still active OR was restarted by systemd watchdog within bounds
  STATE_POST="$(systemctl is-active "$UNIT" || true)"
  N_RESTARTS_END="$(systemctl show -p NRestarts --value "$UNIT")"
  RESTART_DELTA=$(( N_RESTARTS_END - N_RESTARTS_START ))
  if [ "$STATE_POST" = "active" ]; then
    pass "Criterion 3b: service still active after silence; NRestarts delta=${RESTART_DELTA}"
    LOG_RESULT_3B="PASS"
  else
    fail "Criterion 3b: service not active after silence (state=${STATE_POST}); NRestarts delta=${RESTART_DELTA}"
    LOG_RESULT_3B="FAIL"
    ANOMALIES+=("Criterion 3b: service state=${STATE_POST} after silence (expected active); NRestarts delta=${RESTART_DELTA}.")
  fi

  if [ "$LOG_RESULT_3A" = "PASS" ] && [ "$LOG_RESULT_3B" = "PASS" ]; then
    RESULTS[3]="PASS (warning logged + service active; NRestarts delta=${RESTART_DELTA})"
  else
    RESULTS[3]="FAIL (3a=${LOG_RESULT_3A}, 3b=${LOG_RESULT_3B}; NRestarts delta=${RESTART_DELTA})"
  fi
fi

# ========================================================================
# Criterion 4: BMP280 columns populated on recent rows
# ========================================================================
hdr "Criterion 4: BMP280 columns non-NULL on recent rows"
info "waiting 30s for fresh rows to accumulate after recovery..."
sleep 30
NULL_COUNT="$(sqlite3 "$DB" "
  SELECT COUNT(*) FROM (
    SELECT detector_pressure_hpa, detector_temp_c
      FROM muon_events ORDER BY id DESC LIMIT 20
  ) WHERE detector_pressure_hpa IS NULL OR detector_temp_c IS NULL;
")"
SAMPLE="$(sqlite3 "$DB" "
  SELECT id, detector_pressure_hpa, detector_temp_c
    FROM muon_events ORDER BY id DESC LIMIT 5;
")"
echo "recent rows (id, pressure_hpa, temp_c):"
echo "$SAMPLE"
if [ "$NULL_COUNT" -eq 0 ]; then
  pass "Criterion 4: 0 NULLs in detector_pressure_hpa/detector_temp_c across last 20 rows"
  RESULTS[4]="PASS (0 NULLs in last 20 rows)"
else
  fail "Criterion 4: ${NULL_COUNT} NULLs in last 20 rows"
  RESULTS[4]="FAIL (${NULL_COUNT} NULLs in last 20 rows)"
  ANOMALIES+=("Criterion 4: ${NULL_COUNT} NULL BMP280 readings in last 20 rows — check that the device emits per-event BMP280 fields (02-01 sample.csv showed 8-field per-event protocol).")
fi

# ========================================================================
# Write ACCEPTANCE.md
# ========================================================================
N_RESTARTS_FINAL="$(systemctl show -p NRestarts --value "$UNIT")"
STATE_FINAL="$(systemctl is-active "$UNIT" || true)"

if [ "$FAILED" -ne 0 ]; then
  OVERALL="FAIL"
else
  OVERALL="PASS"
fi

# Build anomalies block
ANOMALIES_MD=""
if [ "${#ANOMALIES[@]}" -gt 0 ]; then
  ANOMALIES_MD=$'\n## Anomalies\n\n'
  for a in "${ANOMALIES[@]}"; do
    ANOMALIES_MD+="- ${a}"$'\n'
  done
else
  ANOMALIES_MD=$'\n## Anomalies\n\nNone.\n'
fi

cat > "$ACC" << EOF
---
phase: 02-muon-detector
plan: 07
date: ${TS_NOW}
operator: ${OPERATOR}
result: ${OVERALL}
---

# Phase 2 Acceptance — Muon Detector

This record was produced by \`scripts/verify-muon.sh\` running on the Pi.

## Environment

- Pi hostname: ${HOSTNAME_S}
- Operator: ${OPERATOR}
- Date: ${TS_NOW}
- chrony offset at start: ${OFFSET}s
- DB path: ${DB}
- Unit: ${UNIT}
- Unit path: ${UNIT_PATH}
- /dev/picomuon -> ${DEV_TARGET}
- NRestarts at script start: ${N_RESTARTS_START}
- NRestarts at script end:   ${N_RESTARTS_FINAL}
- Service state at end:      ${STATE_FINAL}

## Results

| # | Criterion                                                            | Result |
|---|----------------------------------------------------------------------|--------|
| 1 | muon_events rows grow continuously                                   | ${RESULTS[1]} |
| 2 | Unplug/replug recovers within 30s without manual restart             | ${RESULTS[2]} |
| 3 | 60s silence: WARNING logged + watchdog maintained                    | ${RESULTS[3]} |
| 4 | detector_pressure_hpa + detector_temp_c populated on recent rows     | ${RESULTS[4]} |

## Evidence — Recent muon_events rows

\`\`\`
${SAMPLE}
\`\`\`
${ANOMALIES_MD}
## Sign-off

- Overall: ${OVERALL}
- Date: ${TS_NOW}
- Operator: ${OPERATOR}
EOF

echo ""
info "wrote ${ACC}"

echo ""
if [ "$FAILED" -eq 0 ]; then
  pass "ALL CRITERIA PASS"
  exit 0
else
  fail "ONE OR MORE CRITERIA FAILED — see ${ACC}"
  exit 1
fi
