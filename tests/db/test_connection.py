"""DATA-02: get_conn() enforces WAL, busy_timeout=5000, synchronous=NORMAL, foreign_keys=ON
on every new connection."""

from __future__ import annotations

from pathlib import Path

from observatory.db.connection import get_conn, get_write_conn


def test_wal_mode(tmp_db_path: Path) -> None:
    conn = get_conn(str(tmp_db_path))
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal", f"expected wal, got {mode!r}"
    conn.close()


def test_busy_timeout(tmp_db_path: Path) -> None:
    conn = get_conn(str(tmp_db_path))
    timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
    assert timeout == 5000, f"expected 5000, got {timeout!r}"
    conn.close()


def test_synchronous_normal(tmp_db_path: Path) -> None:
    conn = get_conn(str(tmp_db_path))
    # PRAGMA synchronous returns integer: 0=OFF, 1=NORMAL, 2=FULL, 3=EXTRA
    sync = conn.execute("PRAGMA synchronous").fetchone()[0]
    assert sync == 1, f"expected 1 (NORMAL), got {sync!r}"
    conn.close()


def test_foreign_keys_on(tmp_db_path: Path) -> None:
    conn = get_conn(str(tmp_db_path))
    fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert fk == 1, f"expected 1, got {fk!r}"
    conn.close()


def test_pragmas_applied_per_new_connection(tmp_db_path: Path) -> None:
    """busy_timeout is per-connection — confirm a second connection also has it."""
    c1 = get_conn(str(tmp_db_path))
    c1.close()
    c2 = get_conn(str(tmp_db_path))
    timeout = c2.execute("PRAGMA busy_timeout").fetchone()[0]
    assert timeout == 5000
    c2.close()


def test_begin_immediate_succeeds(tmp_db_path: Path) -> None:
    """Write transaction pattern works end-to-end."""
    setup = get_conn(str(tmp_db_path))
    setup.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    setup.close()

    conn = get_write_conn(str(tmp_db_path))
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("INSERT INTO t (v) VALUES (?)", ("hello",))
    conn.execute("COMMIT")
    rows = conn.execute("SELECT v FROM t").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "hello"
    conn.close()
