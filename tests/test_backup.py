"""DATA-04: backup creates .db + .ok sentinel; fails fast on missing mount; prunes 14d+; idempotent same-day."""
from __future__ import annotations

import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

# Make scripts/ importable as a module
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import backup as backup_mod  # type: ignore[import-not-found]  # noqa: E402


@pytest.fixture
def populated_source_db(tmp_path: Path) -> Path:
    """A small SQLite DB with one table and a few rows."""
    db = tmp_path / "src.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.executemany(
        "INSERT INTO t (v) VALUES (?)", [("a",), ("b",), ("c",)]
    )
    conn.commit()
    conn.close()
    return db


def test_backup_fails_if_mount_missing(
    populated_source_db: Path, tmp_path: Path
) -> None:
    fake_mount = tmp_path / "not-mounted"
    fake_mount.mkdir()
    # tmp dirs are NOT real mountpoints, so is_mount() returns False naturally
    rc = backup_mod.run_backup(
        source_db=populated_source_db, backup_mount=fake_mount
    )
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
