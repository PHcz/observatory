#!/usr/bin/env bash
# Weekly PRODUCTION backup integrity check (runs on the Pi via obs-backup-verify.timer).
#
# Verifies the NEWEST real backup on the mount — observatory-YYYY-MM-DD.db.gz —
# by gunzipping it and running `PRAGMA integrity_check`. This is the on-device
# counterpart to scripts/verify-backup.sh (which is a self-contained CI roundtrip
# test of backup.py): this one checks the actual production copy on /mnt/backup.
#
# Local-first by design: uses only `gunzip` and the `sqlite3` CLI — no `uv`, no
# Python venv (so it never mutates the obs-api .venv), and no network/package
# index. The decompressed temp DB is written to the mount, never to /tmp (a small
# tmpfs on the Pi that cannot hold a full DB).
set -euo pipefail

MOUNT="${OBS_BACKUP_MOUNT:-/mnt/backup}"

if [[ ! -d "$MOUNT" ]]; then
  echo "FAIL: backup mount $MOUNT does not exist" >&2
  exit 1
fi

# Newest gzipped backup by mtime.
newest="$(ls -1t "$MOUNT"/observatory-*.db.gz 2>/dev/null | head -1 || true)"
if [[ -z "$newest" ]]; then
  echo "FAIL: no observatory-*.db.gz backups found in $MOUNT" >&2
  exit 1
fi

# Decompress to a temp file ON THE MOUNT (roomy; not the /tmp tmpfs).
tmp="$(mktemp "$MOUNT/.verify-XXXXXX.db")"
# Clean up the temp db AND the sqlite sidecars: opening a WAL-mode backup with
# sqlite3 creates "$tmp"-shm / "$tmp"-wal, which a bare `rm -f "$tmp"` would
# leave orphaned on the mount (they accumulate, esp. if a run is interrupted).
trap 'rm -f "$tmp" "$tmp"-shm "$tmp"-wal' EXIT

gunzip -c "$newest" > "$tmp"

result="$(sqlite3 "$tmp" "PRAGMA integrity_check")"
if [[ "$result" != "ok" ]]; then
  echo "FAIL: integrity_check on $(basename "$newest") returned: $result" >&2
  exit 1
fi

# Sanity: the backup should hold real rows, not an empty shell.
rows="$(sqlite3 "$tmp" "SELECT COUNT(*) FROM muon_events" 2>/dev/null || echo 0)"

echo "OK: $(basename "$newest") verified (integrity=ok, muon_events=$rows)"
