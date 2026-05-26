"""Phase 6 — tests for GET /api/weather time-series endpoint.

Plan 06-03 TDD RED phase. Tests use a local FastAPI app with the weather router
mounted in isolation (Plan 06-07 wires the full app; these tests exercise the
router in isolation).
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from observatory.api.routers import weather as weather_router


@pytest.fixture
def client(_ensure_settings_loaded: Path) -> TestClient:
    """Isolated FastAPI app with only the weather router mounted."""
    app = FastAPI()
    app.include_router(weather_router.router, prefix="/api")
    return TestClient(app)


@pytest.fixture
def db_path(_ensure_settings_loaded: Path) -> Path:
    return _ensure_settings_loaded


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_weather(conn: sqlite3.Connection, ts: int, **kwargs: object) -> None:
    conn.execute(
        """
        INSERT INTO weather
          (node_id, ts, temp_c, humidity_pct, pressure_hpa, lux, battery_v, wifi_rssi)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            kwargs.get("node_id", "test"),
            ts,
            kwargs.get("temp_c", 20.0),
            kwargs.get("humidity_pct", 55.0),
            kwargs.get("pressure_hpa", 1013.25),
            kwargs.get("lux", 100.0),
            kwargs.get("battery_v", 3.7),
            kwargs.get("wifi_rssi", -60),
        ),
    )


# ---------------------------------------------------------------------------
# Response shape
# ---------------------------------------------------------------------------


def test_response_shape(client: TestClient) -> None:
    """Response always has exactly these top-level keys."""
    resp = client.get("/api/weather")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"window", "bucket_size_sec", "agg", "rows"}
    assert set(body["window"].keys()) == {"from", "to"}


# ---------------------------------------------------------------------------
# Empty DB
# ---------------------------------------------------------------------------


def test_empty_db_returns_200_with_empty_rows(client: TestClient) -> None:
    resp = client.get("/api/weather")
    assert resp.status_code == 200
    body = resp.json()
    assert body["rows"] == []
    assert "window" in body
    assert "bucket_size_sec" in body


# ---------------------------------------------------------------------------
# Default window
# ---------------------------------------------------------------------------


def test_default_window_is_24h(client: TestClient) -> None:
    now = int(time.time())
    resp = client.get("/api/weather")
    assert resp.status_code == 200
    body = resp.json()
    win = body["window"]
    assert abs(win["to"] - now) < 5  # within 5 seconds of now
    assert win["from"] == win["to"] - 86400


# ---------------------------------------------------------------------------
# Raw rows (short window -> auto=raw)
# ---------------------------------------------------------------------------


def test_short_window_returns_raw_rows(client: TestClient, db_path: Path) -> None:
    """1h window -> auto resolves to raw; 10 seeded rows should all come back."""
    now = int(time.time())
    conn = sqlite3.connect(str(db_path))
    for i in range(10):
        _insert_weather(conn, now - i * 60)
    conn.commit()
    conn.close()

    from_ts = now - 3600
    resp = client.get(f"/api/weather?from={from_ts}&to={now}")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["rows"]) == 10
    assert body["agg"] == "raw"
    # Raw rows must have ts as integer epoch
    for row in body["rows"]:
        assert isinstance(row["ts"], int)


# ---------------------------------------------------------------------------
# Minute-bucketed (24h window)
# ---------------------------------------------------------------------------


def test_24h_window_minute_bucketed(client: TestClient, db_path: Path) -> None:
    """24h window -> auto resolves to minute; 200 rows at 7-min spacing returns ~29 buckets."""
    now = int(time.time())
    conn = sqlite3.connect(str(db_path))
    for i in range(200):
        _insert_weather(conn, now - i * 7 * 60)
    conn.commit()
    conn.close()

    from_ts = now - 86400
    resp = client.get(f"/api/weather?from={from_ts}&to={now}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["agg"] == "minute"
    # Each bucketed row must have averaged fields
    assert len(body["rows"]) > 0
    row0 = body["rows"][0]
    assert "ts" in row0
    assert "temp_c" in row0
    assert "humidity_pct" in row0
    assert "pressure_hpa" in row0
    assert "lux" in row0


# ---------------------------------------------------------------------------
# Explicit agg=hour
# ---------------------------------------------------------------------------


def test_explicit_agg_hour_returns_hourly_buckets(client: TestClient, db_path: Path) -> None:
    """agg=hour on 24h window returns ≤25 rows, each with AVG values."""
    now = int(time.time())
    conn = sqlite3.connect(str(db_path))
    # Seed 200 rows spread over 24h (every 7min) so there's data in each hour
    for i in range(200):
        _insert_weather(conn, now - i * 7 * 60)
    conn.commit()
    conn.close()

    from_ts = now - 86400
    resp = client.get(f"/api/weather?from={from_ts}&to={now}&agg=hour")
    assert resp.status_code == 200
    body = resp.json()
    assert body["agg"] == "hour"
    assert body["bucket_size_sec"] == 3600
    assert len(body["rows"]) <= 25


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


def test_from_gt_to_returns_422(client: TestClient) -> None:
    resp = client.get("/api/weather?from=2000&to=1000")
    assert resp.status_code == 422


def test_invalid_agg_returns_422(client: TestClient) -> None:
    resp = client.get("/api/weather?agg=bogus")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Rounding
# ---------------------------------------------------------------------------


def test_bucketed_values_are_rounded(client: TestClient, db_path: Path) -> None:
    """AVG values must be rounded to expected precision."""
    now = int(time.time())
    conn = sqlite3.connect(str(db_path))
    # Seed two rows in the same minute bucket with known values
    _insert_weather(
        conn,
        now - 86400 + 30,
        temp_c=20.123456,
        humidity_pct=55.678,
        pressure_hpa=1013.12345,
        lux=100.5678,
    )
    _insert_weather(
        conn,
        now - 86400 + 60,
        temp_c=21.876544,
        humidity_pct=54.322,
        pressure_hpa=1014.87655,
        lux=99.4322,
    )
    conn.commit()
    conn.close()

    from_ts = now - 86400
    resp = client.get(f"/api/weather?from={from_ts}&to={now}&agg=minute")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["rows"]) > 0
    row = body["rows"][0]
    # temp_c: 2dp
    assert round(row["temp_c"], 2) == row["temp_c"]
    # humidity_pct: 1dp
    assert round(row["humidity_pct"], 1) == row["humidity_pct"]
    # pressure_hpa: 2dp
    assert round(row["pressure_hpa"], 2) == row["pressure_hpa"]
    # lux: 1dp
    assert round(row["lux"], 1) == row["lux"]
