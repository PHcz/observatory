#!/usr/bin/env python3
"""Daily SQLite backup with integrity check and 14-day retention.

Uses sqlite3.Connection.backup() — WAL-coherent snapshot, not a raw file copy.
Fails fast (exit 1) if /mnt/backup is not actually mounted.
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import structlog

from observatory.logging import configure_logging

# Paths — overridable by tests via module-level patching.
BACKUP_MOUNT = Path("/mnt/backup")
SOURCE_DB = Path("/var/lib/observatory/observatory.db")
RETENTION_DAYS = 14

log = structlog.get_logger()


def _row_count(conn: sqlite3.Connection, table: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    return int(row[0])


def _all_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '_yoyo_%'"
    ).fetchall()
    return [r[0] for r in rows]


def _prune(mount: Path, retention_days: int, today: date) -> int:
    """Delete .db + .ok pairs older than retention_days. Returns count deleted."""
    cutoff = today - timedelta(days=retention_days)
    deleted = 0
    for f in sorted(mount.glob("observatory-*.db")):
        stem = f.stem  # "observatory-YYYY-MM-DD"
        try:
            file_date = date.fromisoformat(stem.replace("observatory-", ""))
        except ValueError:
            continue
        if file_date < cutoff:
            f.unlink(missing_ok=True)
            ok = mount / f"{stem}.ok"
            ok.unlink(missing_ok=True)
            deleted += 1
            log.info("backup.pruned", file=str(f))
    return deleted


def run_backup(
    source_db: Path | None = None,
    backup_mount: Path | None = None,
    retention_days: int = RETENTION_DAYS,
    today: date | None = None,
) -> int:
    """Return 0 on success, 1 on failure. All paths overridable for tests."""
    source = source_db or SOURCE_DB
    mount = backup_mount or BACKUP_MOUNT
    today = today or date.today()

    # 1. Fail fast if mount is not actually mounted (prevents silent SD-card backups)
    if not mount.is_mount():
        log.error("backup.mount_missing", path=str(mount))
        return 1

    dest_db = mount / f"observatory-{today.isoformat()}.db"
    sentinel = mount / f"observatory-{today.isoformat()}.ok"

    # 2. Skip if today's backup already exists and is valid (idempotent within a day)
    if sentinel.exists():
        log.info("backup.already_done", date=today.isoformat())
        return 0

    # 3. Backup via SQLite Online Backup API
    try:
        src = sqlite3.connect(str(source))
        try:
            dst = sqlite3.connect(str(dest_db))
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
    except Exception as e:
        log.error("backup.failed", error=str(e))
        dest_db.unlink(missing_ok=True)
        return 1

    # 4. Verify integrity of the backup file
    check = sqlite3.connect(str(dest_db))
    try:
        result = check.execute("PRAGMA integrity_check").fetchone()
        if result is None or result[0] != "ok":
            log.error("backup.integrity_failed", result=result[0] if result else None)
            check.close()
            dest_db.unlink(missing_ok=True)
            return 1

        # 5. Cross-check row counts — direction-only.
        #
        # sqlite3.Connection.backup() is WAL-coherent: dst is a snapshot of src at
        # the moment backup() returns. Re-reading src here happens AFTER backup()
        # completes, so live writers (e.g. muon detector at ~80 events/min) will
        # have appended more rows to src in the interim. That's expected and OK.
        #
        # The corruption signal we care about is dst_n > src_n (destination has
        # rows the source doesn't — physically impossible for append-only tables;
        # would indicate write corruption or wrong file). Equality and src_n >=
        # dst_n are both healthy outcomes.
        src_conn = sqlite3.connect(str(source))
        try:
            for table in _all_tables(src_conn):
                src_n = _row_count(src_conn, table)
                dst_n = _row_count(check, table)
                if dst_n > src_n:
                    log.error(
                        "backup.row_count_inverted",
                        table=table,
                        src=src_n,
                        dst=dst_n,
                        hint="destination has more rows than source — corruption or wrong file",
                    )
                    check.close()
                    dest_db.unlink(missing_ok=True)
                    return 1
                if src_n != dst_n:
                    # Healthy drift — log at info so operators can see live-write activity
                    log.info(
                        "backup.row_count_drift",
                        table=table,
                        src=src_n,
                        dst=dst_n,
                        drift=src_n - dst_n,
                    )
        finally:
            src_conn.close()
    finally:
        check.close()

    # 6. Write sentinel
    sentinel.write_text(f"ok {today.isoformat()} {datetime.utcnow().isoformat()}Z\n")
    log.info("backup.success", date=today.isoformat(), path=str(dest_db))

    # 7. Prune
    _prune(mount, retention_days, today)

    return 0


def main() -> int:
    configure_logging()
    return run_backup()


if __name__ == "__main__":
    sys.exit(main())
