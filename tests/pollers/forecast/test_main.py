"""RED tests for the forecast poller __main__ (Phase 10, FCAST-01).

Imports `main` from observatory.pollers.forecast.__main__, which Wave 1
(plan 10-02) creates -> import fails RED until then.

Exit-code + audit contract (mirrors noaa/__main__):
  - fetch failure (RetriesExhausted) -> exit 1, status='transient_fail', no rows
  - parse failure (ValueError)        -> exit 1, status='parse_fail', no rows
  - success                            -> exit 0, rows written, status='success'
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import observatory.pollers.forecast.__main__ as forecast_main
from observatory.db import connection as db_conn_mod
from observatory.pollers._http import RetriesExhausted

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "forecast" / "sample.json"


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
        .execute("SELECT status FROM poller_runs WHERE source = 'forecast'")
        .fetchall()
    )


def test_fetch_failure_returns_1_and_audits_transient_fail(
    monkeypatch: pytest.MonkeyPatch, patched_db: Path
) -> None:
    def _boom(*_a: object, **_k: object) -> bytes:
        raise RetriesExhausted("network down")

    monkeypatch.setattr(forecast_main, "fetch", _boom)
    assert forecast_main.main() == 1
    rows = _poller_runs(patched_db)
    assert rows == [("transient_fail",)]
    assert (
        sqlite3.connect(str(patched_db))
        .execute("SELECT COUNT(*) FROM forecast_hourly")
        .fetchone()[0]
        == 0
    )


def test_parse_failure_returns_1_and_audits_parse_fail(
    monkeypatch: pytest.MonkeyPatch, patched_db: Path
) -> None:
    monkeypatch.setattr(forecast_main, "fetch", lambda *_a, **_k: b"not json at all")
    assert forecast_main.main() == 1
    rows = _poller_runs(patched_db)
    assert rows == [("parse_fail",)]


def test_success_returns_0_and_writes_rows(
    monkeypatch: pytest.MonkeyPatch, patched_db: Path
) -> None:
    body = FIXTURE.read_bytes()
    monkeypatch.setattr(forecast_main, "fetch", lambda *_a, **_k: body)
    assert forecast_main.main() == 0
    conn = sqlite3.connect(str(patched_db))
    assert conn.execute("SELECT COUNT(*) FROM forecast_hourly").fetchone()[0] > 0
    assert conn.execute("SELECT COUNT(*) FROM forecast_daily").fetchone()[0] == 7
    assert _poller_runs(patched_db) == [("success",)]
