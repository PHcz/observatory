"""RED tests for write_forecast (replace-on-fetch + poller_runs audit).

Phase 10, FCAST-02. Imports write_forecast + the dataclasses, which Wave 1
(plan 10-02) creates -> import fails RED until then.

Replace-on-fetch contract (10-RESEARCH Pattern 3): the cache holds exactly ONE
current forecast; a second write replaces the first (old ts keys gone). The
poller_runs audit row is ALWAYS emitted (two-transaction discipline), even on a
failure status with no data rows.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from observatory.pollers._types import (
    ForecastDaily,
    ForecastHourly,
)
from observatory.pollers._write import write_forecast


def _patch_get_write_conn(monkeypatch: pytest.MonkeyPatch, db_path: Path) -> None:
    def _factory(_path: str | None = None) -> sqlite3.Connection:
        from observatory.db.connection import get_conn

        return get_conn(str(db_path))

    monkeypatch.setattr("observatory.pollers._write.get_write_conn", _factory)


def _h(ts: int) -> ForecastHourly:
    return ForecastHourly(
        ts=ts,
        temp_c=15.0,
        apparent_temp_c=14.0,
        relative_humidity_pct=70,
        surface_pressure_hpa=1012.0,
        precip_prob_pct=10,
        weather_code=3,
        wind_speed_kmh=12.0,
    )


def _d(ts: int) -> ForecastDaily:
    return ForecastDaily(
        ts=ts,
        temp_max_c=18.0,
        temp_min_c=10.0,
        precip_prob_max_pct=30,
        weather_code=61,
        wind_speed_max_kmh=24.0,
    )


def _meta(fetched_at: int = 1000) -> dict:
    return {"utc_offset_seconds": 3600, "timezone": "Europe/London", "fetched_at": fetched_at}


def test_write_inserts_rows_and_meta(monkeypatch: pytest.MonkeyPatch, tmp_db: Path) -> None:
    _patch_get_write_conn(monkeypatch, tmp_db)
    write_forecast(
        [_h(100), _h(200)],
        [_d(50)],
        _meta(1000),
        started_at=1,
        status="success",
        error_summary=None,
    )
    conn = sqlite3.connect(str(tmp_db))
    assert conn.execute("SELECT COUNT(*) FROM forecast_hourly").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM forecast_daily").fetchone()[0] == 1
    meta_rows = conn.execute("SELECT COUNT(*), MAX(fetched_at) FROM forecast_meta").fetchone()
    assert meta_rows[0] == 1
    assert meta_rows[1] == 1000


def test_write_replaces_not_appends(monkeypatch: pytest.MonkeyPatch, tmp_db: Path) -> None:
    _patch_get_write_conn(monkeypatch, tmp_db)
    write_forecast(
        [_h(100), _h(200)],
        [_d(50)],
        _meta(1000),
        started_at=1,
        status="success",
        error_summary=None,
    )
    # Second forecast with DIFFERENT ts keys (horizon shifted).
    write_forecast(
        [_h(300), _h(400)],
        [_d(60)],
        _meta(2000),
        started_at=2,
        status="success",
        error_summary=None,
    )
    conn = sqlite3.connect(str(tmp_db))
    hourly_ts = {r[0] for r in conn.execute("SELECT ts FROM forecast_hourly")}
    assert hourly_ts == {300, 400}  # old keys gone
    assert conn.execute("SELECT COUNT(*) FROM forecast_daily").fetchone()[0] == 1
    assert conn.execute("SELECT ts FROM forecast_daily").fetchone()[0] == 60


def test_write_always_emits_poller_runs(monkeypatch: pytest.MonkeyPatch, tmp_db: Path) -> None:
    _patch_get_write_conn(monkeypatch, tmp_db)
    write_forecast(
        [_h(100)], [_d(50)], _meta(1000), started_at=1, status="success", error_summary=None
    )
    conn = sqlite3.connect(str(tmp_db))
    rows = conn.execute(
        "SELECT source, status FROM poller_runs WHERE source = 'forecast'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][1] == "success"


def test_failure_status_writes_no_rows_but_audits(
    monkeypatch: pytest.MonkeyPatch, tmp_db: Path
) -> None:
    _patch_get_write_conn(monkeypatch, tmp_db)
    write_forecast([], [], None, started_at=1, status="transient_fail", error_summary="fetch:X")
    conn = sqlite3.connect(str(tmp_db))
    assert conn.execute("SELECT COUNT(*) FROM forecast_hourly").fetchone()[0] == 0
    rows = conn.execute("SELECT status FROM poller_runs WHERE source = 'forecast'").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "transient_fail"
