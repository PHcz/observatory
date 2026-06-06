"""RED integration tests for GET /api/forecast (Phase 10, FCAST-02 + FCAST-04).

The forecast router is created in Wave 2 (plan 10-03). Until then these requests
404 (route absent) -> the assertions fail RED, which is the expected Wave-0 state.

Seeds forecast_hourly/forecast_daily/forecast_meta + weather rows in the per-test
tmp DB (the autouse `health_db` fixture applies migration 0005), then asserts the
cache-serve, empty-state, and forecast-vs-actual contracts:
  - empty tables -> 200 empty-state body (NOT 404) (10-RESEARCH Pattern 2)
  - hourly window is next-24h relative to now, ascending, capped (Pitfall 3)
  - vs-actual uses the LOCAL-day boundary, signed delta + label (Pitfall 4)
  - empty weather -> vs_actual per-metric actual is null, no 500 (Pitfall 5)
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


def _seed_hourly(
    conn: sqlite3.Connection, ts: int, *, temp: float = 15.0, fetched_at: int = 1000
) -> None:
    conn.execute(
        "INSERT INTO forecast_hourly (ts, temp_c, apparent_temp_c, relative_humidity_pct, "
        "surface_pressure_hpa, precip_prob_pct, weather_code, wind_speed_kmh, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (ts, temp, temp - 1, 70, 1012.0, 10, 3, 12.0, fetched_at),
    )


def _seed_daily(
    conn: sqlite3.Connection,
    ts: int,
    *,
    tmax: float = 18.0,
    tmin: float = 10.0,
    fetched_at: int = 1000,
) -> None:
    conn.execute(
        "INSERT INTO forecast_daily (ts, temp_max_c, temp_min_c, precip_prob_max_pct, "
        "weather_code, wind_speed_max_kmh, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (ts, tmax, tmin, 30, 61, 24.0, fetched_at),
    )


def _seed_meta(conn: sqlite3.Connection, fetched_at: int = 1000, offset: int = 3600) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO forecast_meta (id, fetched_at, utc_offset_seconds, timezone) "
        "VALUES (1, ?, ?, ?)",
        (fetched_at, offset, "Europe/London"),
    )


def _seed_weather(conn: sqlite3.Connection, ts: int, temp: float) -> None:
    conn.execute(
        "INSERT INTO weather (node_id, ts, temp_c, humidity_pct, pressure_hpa) "
        "VALUES (?, ?, ?, ?, ?)",
        ("test-node", ts, temp, 65.0, 1010.0),
    )


def test_empty_tables_return_empty_state_not_404(api_client: TestClient) -> None:
    r = api_client.get("/api/forecast")
    assert r.status_code == 200
    body = r.json()
    assert body["hourly"] == []
    assert body["daily"] == []
    assert body["vs_actual"] is None
    assert body["fetched_at"] is None


def test_serves_cached_rows_next_24h(api_client: TestClient, health_db: Path) -> None:
    now = int(time.time())
    conn = sqlite3.connect(str(health_db), isolation_level=None)
    try:
        # 2 past hours + 30 future hours
        for h in range(-2, 30):
            _seed_hourly(conn, now + h * 3600)
        _seed_meta(conn)
    finally:
        conn.close()

    body = api_client.get("/api/forecast").json()
    ts_list = [h["ts"] for h in body["hourly"]]
    assert ts_list, "expected some hourly rows"
    assert all(t >= now for t in ts_list)  # no past hours
    assert len(ts_list) <= 24
    assert ts_list == sorted(ts_list)  # ascending


def test_serves_7_daily_rows(api_client: TestClient, health_db: Path) -> None:
    now = int(time.time())
    day = now - now % 86400
    conn = sqlite3.connect(str(health_db), isolation_level=None)
    try:
        for d in range(7):
            _seed_daily(conn, day + d * 86400)
        _seed_meta(conn)
    finally:
        conn.close()

    body = api_client.get("/api/forecast").json()
    ts_list = [d["ts"] for d in body["daily"]]
    assert len(ts_list) == 7
    assert ts_list == sorted(ts_list)


def test_vs_actual_temp_cool(api_client: TestClient, health_db: Path) -> None:
    now = int(time.time())
    offset = 0  # GMT for deterministic local-day math
    local_day = now - now % 86400
    conn = sqlite3.connect(str(health_db), isolation_level=None)
    try:
        _seed_daily(conn, local_day, tmax=18.0, tmin=10.0)
        _seed_meta(conn, offset=offset)
        # Measured max within today's local day = 16 (forecast 18 -> running 2 cool)
        _seed_weather(conn, local_day + 3600, 12.0)
        _seed_weather(conn, local_day + 7200, 16.0)
    finally:
        conn.close()

    body = api_client.get("/api/forecast").json()
    temp = body["vs_actual"]["temp"]
    # signed delta present + a cool label; warn only when |delta| >= 3
    assert "cool" in str(temp).lower()


def test_vs_actual_local_day_boundary(api_client: TestClient, health_db: Path) -> None:
    now = int(time.time())
    offset = 3600  # BST: local day starts 1h before the UTC day
    local_day = now - now % 86400  # forecast_daily.ts[0] = local-day start (already UTC epoch)
    conn = sqlite3.connect(str(health_db), isolation_level=None)
    try:
        _seed_daily(conn, local_day, tmax=18.0, tmin=10.0)
        _seed_meta(conn, offset=offset)
        # A reading just before the local-day window must be EXCLUDED, one inside INCLUDED.
        _seed_weather(conn, local_day - 1800, 99.0)  # outside local day -> must be ignored
        _seed_weather(conn, local_day + 1800, 14.0)  # inside local day
    finally:
        conn.close()

    body = api_client.get("/api/forecast").json()
    # If the boundary were UTC-day the 99.0 reading would pollute actual max.
    assert "99" not in str(body["vs_actual"]["temp"])


def test_vs_actual_empty_weather_actual_null(api_client: TestClient, health_db: Path) -> None:
    now = int(time.time())
    local_day = now - now % 86400
    conn = sqlite3.connect(str(health_db), isolation_level=None)
    try:
        _seed_daily(conn, local_day, tmax=18.0, tmin=10.0)
        _seed_meta(conn, offset=0)
        # NO weather rows.
    finally:
        conn.close()

    r = api_client.get("/api/forecast")
    assert r.status_code == 200  # no crash on empty weather
    temp = r.json()["vs_actual"]["temp"]
    assert temp["actual"] is None
