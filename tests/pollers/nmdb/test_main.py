"""RED tests for the NMDB poller __main__ (Phase 13, MU2-06).

Imports `main` from observatory.pollers.nmdb.__main__, which Wave 1 (plan 13-03)
creates -> import fails RED until then.

Exit-code + audit contract (mirrors airquality/forecast __main__):
  - fetch failure (RetriesExhausted) -> exit 1, status='transient_fail', no rows
  - parse failure (ValueError)        -> exit 1, status='parse_fail', no rows
  - success                            -> exit 0, rows written, status='success'
The poller_runs audit row is always present.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import observatory.pollers.nmdb.__main__ as nmdb_main
from observatory.db import connection as db_conn_mod
from observatory.pollers._http import RetriesExhausted

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "nmdb" / "sample.txt"


@pytest.fixture
def patched_db(monkeypatch: pytest.MonkeyPatch, tmp_db: Path) -> Path:
    def _factory(_path: str | None = None) -> sqlite3.Connection:
        conn = sqlite3.connect(str(tmp_db), isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    monkeypatch.setattr(db_conn_mod, "get_conn", _factory)
    monkeypatch.setattr(db_conn_mod, "get_write_conn", _factory)
    import observatory.pollers._write as _write_mod

    monkeypatch.setattr(_write_mod, "get_write_conn", _factory, raising=False)
    return tmp_db


def _poller_runs(db: Path) -> list[tuple]:
    return (
        sqlite3.connect(str(db))
        .execute("SELECT status FROM poller_runs WHERE source = 'nmdb'")
        .fetchall()
    )


def test_fetch_failure_returns_1_and_audits_transient_fail(
    monkeypatch: pytest.MonkeyPatch, patched_db: Path
) -> None:
    def _boom(*_a: object, **_k: object) -> bytes:
        raise RetriesExhausted("network down")

    monkeypatch.setattr(nmdb_main, "fetch", _boom)
    assert nmdb_main.main() == 1
    assert _poller_runs(patched_db) == [("transient_fail",)]
    assert (
        sqlite3.connect(str(patched_db)).execute("SELECT COUNT(*) FROM nmdb_counts").fetchone()[0]
        == 0
    )


def test_parse_failure_returns_1_and_audits_parse_fail(
    monkeypatch: pytest.MonkeyPatch, patched_db: Path
) -> None:
    monkeypatch.setattr(nmdb_main, "fetch", lambda *_a, **_k: b"<html><pre></pre></html>")
    assert nmdb_main.main() == 1
    assert _poller_runs(patched_db) == [("parse_fail",)]


def test_success_returns_0_and_writes_rows(
    monkeypatch: pytest.MonkeyPatch, patched_db: Path
) -> None:
    body = FIXTURE.read_bytes()
    monkeypatch.setattr(nmdb_main, "fetch", lambda *_a, **_k: body)
    assert nmdb_main.main() == 0
    conn = sqlite3.connect(str(patched_db))
    assert conn.execute("SELECT COUNT(*) FROM nmdb_counts").fetchone()[0] > 0
    assert _poller_runs(patched_db) == [("success",)]
