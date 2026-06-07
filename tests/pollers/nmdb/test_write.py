"""RED tests for write_nmdb (append window + dedup + poller_runs audit).

Phase 13, MU2-06. Imports write_nmdb + the NmdbCount dataclass, which Wave 1
(plan 13-03) creates -> import fails RED until then.

Append-window contract: rows are INSERT OR IGNORE on UNIQUE(station, ts) so a
re-fetch of an overlapping window does not duplicate rows. nmdb_meta is upserted
(id=1) with the fetched_at freshness anchor. The poller_runs audit row is ALWAYS
emitted (two-transaction discipline), even on a failure status with no data rows.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from observatory.pollers._types import NmdbCount
from observatory.pollers._write import write_nmdb


def _patch_get_write_conn(monkeypatch: pytest.MonkeyPatch, db_path: Path) -> None:
    def _factory(_path: str | None = None) -> sqlite3.Connection:
        from observatory.db.connection import get_conn

        return get_conn(str(db_path))

    monkeypatch.setattr("observatory.pollers._write.get_write_conn", _factory)


def _counts(station: str = "OULU", base_ts: int = 1_700_000_000, n: int = 3) -> list[NmdbCount]:
    return [
        NmdbCount(ts=base_ts + i * 3600, station=station, counts_per_sec=100.0 + i)
        for i in range(n)
    ]


def _meta(fetched_at: int = 1000, station: str = "OULU") -> dict:
    return {"fetched_at": fetched_at, "station": station}


def test_write_appends_rows_and_meta(monkeypatch: pytest.MonkeyPatch, tmp_db: Path) -> None:
    _patch_get_write_conn(monkeypatch, tmp_db)
    write_nmdb(_counts(n=3), _meta(1000), started_at=1, status="success", error_summary=None)
    conn = sqlite3.connect(str(tmp_db))
    assert conn.execute("SELECT COUNT(*) FROM nmdb_counts").fetchone()[0] == 3
    meta_rows = conn.execute("SELECT COUNT(*), MAX(fetched_at) FROM nmdb_meta").fetchone()
    assert meta_rows[0] == 1
    assert meta_rows[1] == 1000
    runs = conn.execute("SELECT source, status FROM poller_runs WHERE source = 'nmdb'").fetchall()
    assert runs == [("nmdb", "success")]


def test_write_dedups_on_unique_station_ts(monkeypatch: pytest.MonkeyPatch, tmp_db: Path) -> None:
    _patch_get_write_conn(monkeypatch, tmp_db)
    write_nmdb(_counts(n=3), _meta(1000), started_at=1, status="success", error_summary=None)
    # Re-fetch overlapping window (same station+ts) -> INSERT OR IGNORE keeps count at 3.
    write_nmdb(_counts(n=3), _meta(2000), started_at=2, status="success", error_summary=None)
    conn = sqlite3.connect(str(tmp_db))
    assert conn.execute("SELECT COUNT(*) FROM nmdb_counts").fetchone()[0] == 3
    # meta upserted to the newer fetched_at.
    assert conn.execute("SELECT fetched_at FROM nmdb_meta WHERE id = 1").fetchone()[0] == 2000


def test_failure_status_writes_no_rows_but_audits(
    monkeypatch: pytest.MonkeyPatch, tmp_db: Path
) -> None:
    _patch_get_write_conn(monkeypatch, tmp_db)
    write_nmdb(None, None, started_at=1, status="transient_fail", error_summary="fetch:X")
    conn = sqlite3.connect(str(tmp_db))
    assert conn.execute("SELECT COUNT(*) FROM nmdb_counts").fetchone()[0] == 0
    rows = conn.execute("SELECT status FROM poller_runs WHERE source = 'nmdb'").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "transient_fail"
