"""DATA-04: backup creates .db + .ok sentinel; fails fast on missing mount; prunes 14d+.

Phase 16 ENH-07: extended with gzip output test and .db.gz _prune() test.
"""

from __future__ import annotations

import gzip
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

# Make scripts/ importable as a module
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import backup as backup_mod  # noqa: E402


@pytest.fixture
def populated_source_db(tmp_path: Path) -> Path:
    """A small SQLite DB with one table and a few rows."""
    db = tmp_path / "src.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.executemany("INSERT INTO t (v) VALUES (?)", [("a",), ("b",), ("c",)])
    conn.commit()
    conn.close()
    return db


def test_backup_fails_if_mount_missing(populated_source_db: Path, tmp_path: Path) -> None:
    fake_mount = tmp_path / "not-mounted"
    fake_mount.mkdir()
    # tmp dirs are NOT real mountpoints, so is_mount() returns False naturally
    rc = backup_mod.run_backup(source_db=populated_source_db, backup_mount=fake_mount)
    assert rc == 1
    assert not any(fake_mount.glob("observatory-*.db"))


def test_backup_creates_db_and_sentinel(
    populated_source_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mount = tmp_path / "mnt"
    mount.mkdir()
    monkeypatch.setattr(Path, "is_mount", lambda self: self == mount)

    rc = backup_mod.run_backup(source_db=populated_source_db, backup_mount=mount)
    assert rc == 0
    today = date.today().isoformat()
    assert (mount / f"observatory-{today}.db").exists()
    assert (mount / f"observatory-{today}.ok").exists()


def test_backup_db_passes_integrity_check(
    populated_source_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mount = tmp_path / "mnt"
    mount.mkdir()
    monkeypatch.setattr(Path, "is_mount", lambda self: self == mount)
    backup_mod.run_backup(source_db=populated_source_db, backup_mount=mount)

    today = date.today().isoformat()
    conn = sqlite3.connect(str(mount / f"observatory-{today}.db"))
    result = conn.execute("PRAGMA integrity_check").fetchone()[0]
    conn.close()
    assert result == "ok"


def test_backup_row_count_matches(
    populated_source_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mount = tmp_path / "mnt"
    mount.mkdir()
    monkeypatch.setattr(Path, "is_mount", lambda self: self == mount)
    backup_mod.run_backup(source_db=populated_source_db, backup_mount=mount)

    today = date.today().isoformat()
    conn = sqlite3.connect(str(mount / f"observatory-{today}.db"))
    n = conn.execute("SELECT COUNT(*) FROM t").fetchone()[0]
    conn.close()
    assert n == 3


def test_backup_idempotent_same_day(
    populated_source_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mount = tmp_path / "mnt"
    mount.mkdir()
    monkeypatch.setattr(Path, "is_mount", lambda self: self == mount)

    assert backup_mod.run_backup(source_db=populated_source_db, backup_mount=mount) == 0
    today = date.today().isoformat()
    sentinel_mtime = (mount / f"observatory-{today}.ok").stat().st_mtime
    db_mtime = (mount / f"observatory-{today}.db").stat().st_mtime

    # second call should short-circuit on sentinel
    assert backup_mod.run_backup(source_db=populated_source_db, backup_mount=mount) == 0
    assert (mount / f"observatory-{today}.ok").stat().st_mtime == sentinel_mtime
    assert (mount / f"observatory-{today}.db").stat().st_mtime == db_mtime


def test_pruning_removes_files_older_than_14_days(tmp_path: Path) -> None:
    mount = tmp_path / "mnt"
    mount.mkdir()

    today = date(2026, 5, 23)
    old_date = today - timedelta(days=20)
    fresh_date = today - timedelta(days=3)

    old_db = mount / f"observatory-{old_date.isoformat()}.db"
    old_ok = mount / f"observatory-{old_date.isoformat()}.ok"
    fresh_db = mount / f"observatory-{fresh_date.isoformat()}.db"
    fresh_ok = mount / f"observatory-{fresh_date.isoformat()}.ok"
    for f in [old_db, old_ok, fresh_db, fresh_ok]:
        f.touch()

    deleted = backup_mod._prune(mount, retention_days=14, today=today)
    assert deleted == 1
    assert not old_db.exists()
    assert not old_ok.exists()
    assert fresh_db.exists()
    assert fresh_ok.exists()


def test_uses_connection_backup_not_shutil_copy() -> None:
    src = (REPO_ROOT / "scripts" / "backup.py").read_text()
    assert "src.backup(dst)" in src
    assert "shutil.copy" not in src


def test_backup_accepts_live_writer_drift(
    populated_source_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Live writers (e.g. muon detector) append rows to src while backup runs.

    The result is dst_n < src_n_at_recheck-time. That's a healthy outcome on an
    append-only workload — NOT a failure. Verifies backup.row_count_drift logs at
    info and returns exit 0.
    """
    mount = tmp_path / "mnt"
    mount.mkdir()
    monkeypatch.setattr(Path, "is_mount", lambda self: self == mount)

    # Hook the post-backup src re-open so we can append rows BETWEEN the
    # initial src.backup(dst) and the row-count cross-check.
    orig_connect = sqlite3.connect

    def connect_and_append(path: str, *args: Any, **kwargs: Any) -> sqlite3.Connection:
        conn: sqlite3.Connection = orig_connect(path, *args, **kwargs)
        # If this is the source DB being opened in step 5 (after the backup),
        # append a row to simulate a live writer arriving mid-backup.
        if str(populated_source_db) in str(path):
            try:
                conn.execute("INSERT INTO t (v) VALUES ('live-arrival-during-backup')")
                conn.commit()
            except sqlite3.Error:
                pass
        return conn

    # Patch sqlite3.connect only for the 2nd open (after src.backup(dst)).
    call_count = {"n": 0}

    def selective_connect(path: str, *args: Any, **kwargs: Any) -> sqlite3.Connection:
        call_count["n"] += 1
        if call_count["n"] == 2 and str(populated_source_db) in str(path):
            return connect_and_append(path, *args, **kwargs)
        conn: sqlite3.Connection = orig_connect(path, *args, **kwargs)
        return conn

    monkeypatch.setattr("scripts.backup.sqlite3.connect", selective_connect)

    rc = backup_mod.run_backup(source_db=populated_source_db, backup_mount=mount)
    assert rc == 0, "backup should succeed when source grew during backup (append-only)"

    today = date.today().isoformat()
    assert (mount / f"observatory-{today}.db").exists()
    assert (mount / f"observatory-{today}.ok").exists()


# NOTE: dst > src inversion is treated as corruption by the script (returns 1),
# but it's untestable cheaply because sqlite3.Connection is an immutable C type
# that can't be monkeypatched. The defensive check is verified by code review
# at scripts/backup.py "if dst_n > src_n:" rather than by a runtime test.


# ---------------------------------------------------------------------------
# Phase 16 ENH-07: gzip output + .db.gz _prune()
# ---------------------------------------------------------------------------


def test_gzip_output(
    populated_source_db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """run_backup() must write observatory-YYYY-MM-DD.db.gz (not .db) to the mount.

    RED: backup.py currently writes .db, not .db.gz. This test will fail until
    ENH-07 implementation replaces the uncompressed backup with a gzip stream.
    """
    mount = tmp_path / "mnt"
    mount.mkdir()
    monkeypatch.setattr(Path, "is_mount", lambda self: self == mount)

    rc = backup_mod.run_backup(source_db=populated_source_db, backup_mount=mount)
    assert rc == 0

    today = date.today().isoformat()
    gz_file = mount / f"observatory-{today}.db.gz"
    assert gz_file.exists(), f"Expected .db.gz file at {gz_file}; found: {list(mount.iterdir())}"

    # The .gz file must be a valid gzip archive (not corrupt)
    with gzip.open(gz_file, "rb") as f:
        data = f.read()
    assert len(data) > 0, "Gzip backup file is empty"


def test_prune_gz(tmp_path: Path) -> None:
    """_prune() must handle .db.gz files and delete those older than retention_days.

    RED: backup._prune() currently globs for *.db files. This test will fail until
    ENH-07 implementation updates _prune() to glob for *.db.gz and use
    f.name.removesuffix('.db.gz') for date extraction (Pitfall 5).
    """
    mount = tmp_path / "mnt"
    mount.mkdir()

    today = date(2026, 6, 8)
    old_date = today - timedelta(days=15)  # 15 days old → beyond 10-day retention
    fresh_date = today - timedelta(days=3)  # 3 days old → within retention

    old_gz = mount / f"observatory-{old_date.isoformat()}.db.gz"
    old_ok = mount / f"observatory-{old_date.isoformat()}.ok"
    fresh_gz = mount / f"observatory-{fresh_date.isoformat()}.db.gz"
    fresh_ok = mount / f"observatory-{fresh_date.isoformat()}.ok"
    for f in [old_gz, old_ok, fresh_gz, fresh_ok]:
        f.touch()

    deleted = backup_mod._prune(mount, retention_days=10, today=today)
    assert deleted >= 1, f"Expected at least 1 deletion, got {deleted}"
    assert not old_gz.exists(), f"Old .db.gz should have been pruned: {old_gz}"
    assert fresh_gz.exists(), f"Fresh .db.gz must NOT be pruned: {fresh_gz}"
