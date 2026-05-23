"""SQLite connection factory enforcing WAL + busy_timeout + foreign_keys on every new connection.

CRITICAL: busy_timeout, synchronous, and foreign_keys are per-connection settings — they do
NOT persist across new connections (unlike journal_mode=WAL, which is stored in the DB file
header). Every writer must use get_conn() so the PRAGMAs are applied.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


def get_conn(db_path: str | None = None) -> sqlite3.Connection:
    """Return a WAL-mode, busy_timeout=5000 configured sqlite3.Connection.

    Args:
        db_path: SQLite file path. If None, reads from observatory.config.settings.
            The override exists primarily for tests and tooling.
    """
    if db_path is None:
        # Lazy import to avoid hard import-time dependency on config at module import.
        from observatory.config import settings

        db_path = settings.observatory_db_path

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path), isolation_level=None)
    conn.row_factory = sqlite3.Row

    # Apply PRAGMAs every time — WAL is persisted, the others are per-connection.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def get_write_conn(db_path: str | None = None) -> sqlite3.Connection:
    """Return a connection intended for write transactions.

    Caller is expected to use `BEGIN IMMEDIATE` before writes:

        with get_write_conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("INSERT INTO weather (...) VALUES (...)", {...})
            conn.execute("COMMIT")
    """
    return get_conn(db_path)
