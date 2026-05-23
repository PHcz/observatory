#!/usr/bin/env bash
# End-to-end backup verification (local; does not require Pi or USB stick).
# Creates a source SQLite DB, runs backup.py against a temp "mount" using a stub
# that overrides Path.is_mount, and verifies output.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

SRC="$TMP/src.db"
MOUNT="$TMP/mount"
mkdir -p "$MOUNT"

# Populate source DB
sqlite3 "$SRC" <<SQL
CREATE TABLE w (id INTEGER PRIMARY KEY, v TEXT);
INSERT INTO w (v) VALUES ('a'), ('b'), ('c');
SQL

# Run backup with Path.is_mount monkeypatched to True for $MOUNT
uv run python - <<PY
import sys
from pathlib import Path
sys.path.insert(0, "$REPO_ROOT/scripts")
import backup
# Pretend $MOUNT is a real mountpoint
orig_is_mount = Path.is_mount
Path.is_mount = lambda self: str(self) == "$MOUNT"
try:
    rc = backup.run_backup(source_db=Path("$SRC"), backup_mount=Path("$MOUNT"))
finally:
    Path.is_mount = orig_is_mount
sys.exit(rc)
PY

TODAY="$(date +%Y-%m-%d)"  # local timezone — must match Python's date.today()
test -f "$MOUNT/observatory-$TODAY.db" || { echo "FAIL: db missing"; exit 1; }
test -f "$MOUNT/observatory-$TODAY.ok" || { echo "FAIL: sentinel missing"; exit 1; }

# Verify integrity of backup file
RESULT="$(sqlite3 "$MOUNT/observatory-$TODAY.db" "PRAGMA integrity_check")"
[ "$RESULT" = "ok" ] || { echo "FAIL: integrity check returned $RESULT"; exit 1; }

# Row count matches
N="$(sqlite3 "$MOUNT/observatory-$TODAY.db" "SELECT COUNT(*) FROM w")"
[ "$N" = "3" ] || { echo "FAIL: row count mismatch ($N != 3)"; exit 1; }

echo "OK: backup verified ($TODAY, 3 rows, integrity=ok)"
