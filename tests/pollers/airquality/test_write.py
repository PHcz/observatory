"""RED tests for write_air_quality (replace-on-fetch + poller_runs audit).

Phase 11, OAQ-01. Imports write_air_quality + the AirQualitySnapshot dataclass,
which Wave 1 (plan 11-02) creates -> import fails RED until then.

Replace-on-fetch contract: the cache holds exactly ONE current snapshot (id=1); a
second write replaces the first. The poller_runs audit row is ALWAYS emitted
(two-transaction discipline), even on a failure status with no data rows.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from observatory.pollers._types import AirQualitySnapshot
from observatory.pollers._write import write_air_quality


def _patch_get_write_conn(monkeypatch: pytest.MonkeyPatch, db_path: Path) -> None:
    def _factory(_path: str | None = None) -> sqlite3.Connection:
        from observatory.db.connection import get_conn

        return get_conn(str(db_path))

    monkeypatch.setattr("observatory.pollers._write.get_write_conn", _factory)


def _snap(aqi: float = 27.0, ts: int = 100) -> AirQualitySnapshot:
    return AirQualitySnapshot(
        ts=ts,
        european_aqi=aqi,
        pm2_5=3.7,
        pm10=11.2,
        nitrogen_dioxide=6.1,
        ozone=68.0,
        sulphur_dioxide=0.4,
        uv_index=0.0,
        alder_pollen=0.0,
        birch_pollen=0.0,
        grass_pollen=6.7,
        mugwort_pollen=0.0,
        olive_pollen=0.0,
        ragweed_pollen=0.0,
    )


def _meta(fetched_at: int = 1000) -> dict:
    return {"utc_offset_seconds": 3600, "timezone": "Europe/London", "fetched_at": fetched_at}


def test_write_inserts_single_row_and_meta(monkeypatch: pytest.MonkeyPatch, tmp_db: Path) -> None:
    _patch_get_write_conn(monkeypatch, tmp_db)
    write_air_quality(_snap(), _meta(1000), started_at=1, status="success", error_summary=None)
    conn = sqlite3.connect(str(tmp_db))
    assert conn.execute("SELECT COUNT(*) FROM air_quality").fetchone()[0] == 1
    assert conn.execute("SELECT id FROM air_quality").fetchone()[0] == 1
    meta_rows = conn.execute("SELECT COUNT(*), MAX(fetched_at) FROM air_quality_meta").fetchone()
    assert meta_rows[0] == 1
    assert meta_rows[1] == 1000
    runs = conn.execute(
        "SELECT source, status FROM poller_runs WHERE source = 'air_quality'"
    ).fetchall()
    assert runs == [("air_quality", "success")]


def test_write_replaces_not_appends(monkeypatch: pytest.MonkeyPatch, tmp_db: Path) -> None:
    _patch_get_write_conn(monkeypatch, tmp_db)
    write_air_quality(
        _snap(aqi=27.0), _meta(1000), started_at=1, status="success", error_summary=None
    )
    write_air_quality(
        _snap(aqi=55.0), _meta(2000), started_at=2, status="success", error_summary=None
    )
    conn = sqlite3.connect(str(tmp_db))
    assert conn.execute("SELECT COUNT(*) FROM air_quality").fetchone()[0] == 1
    assert conn.execute("SELECT european_aqi FROM air_quality WHERE id = 1").fetchone()[0] == 55.0


def test_failure_status_writes_no_row_but_audits(
    monkeypatch: pytest.MonkeyPatch, tmp_db: Path
) -> None:
    _patch_get_write_conn(monkeypatch, tmp_db)
    write_air_quality(None, None, started_at=1, status="transient_fail", error_summary="fetch:X")
    conn = sqlite3.connect(str(tmp_db))
    assert conn.execute("SELECT COUNT(*) FROM air_quality").fetchone()[0] == 0
    rows = conn.execute("SELECT status FROM poller_runs WHERE source = 'air_quality'").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "transient_fail"
