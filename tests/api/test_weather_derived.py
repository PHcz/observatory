"""Phase 16 ENH-05: /api/weather/today and /api/weather/outlook derived endpoints.

RED: these routes do not exist yet.
This test gates Wave 1 implementation.
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
    app = FastAPI()
    app.include_router(weather_router.router, prefix="/api")
    return TestClient(app)


@pytest.fixture
def db_path(_ensure_settings_loaded: Path) -> Path:
    return _ensure_settings_loaded


def _insert_weather(
    conn: sqlite3.Connection,
    ts: int,
    temp_c: float = 15.0,
    humidity_pct: float = 70.0,
    pressure_hpa: float = 1013.0,
    node_id: str = "test-node",
) -> None:
    conn.execute(
        "INSERT INTO weather (node_id, ts, temp_c, humidity_pct, pressure_hpa, lux) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (node_id, ts, temp_c, humidity_pct, pressure_hpa, 100.0),
    )


class TestWeatherToday:
    def test_weather_today_required_keys(self, client: TestClient, db_path: Path) -> None:
        """GET /api/weather/today returns required today-so-far keys."""
        now = int(time.time())
        conn = sqlite3.connect(str(db_path))
        # Seed several readings since midnight (approximate with the last 6 hours)
        for i in range(6):
            _insert_weather(conn, now - i * 3600, temp_c=15.0 + i, pressure_hpa=1013.0 - i)
        conn.commit()
        conn.close()

        resp = client.get("/api/weather/today")
        assert resp.status_code == 200
        body = resp.json()
        required_keys = {
            "high_c",
            "low_c",
            "pressure_high_hpa",
            "pressure_low_hpa",
            "peak_lux",
            "dewpoint_high_c",
            "dewpoint_low_c",
            "since_ts",
        }
        for key in required_keys:
            assert key in body, (
                f"'{key}' missing from /api/weather/today response; got: {list(body.keys())}"
            )

    def test_weather_today_empty_db(self, client: TestClient) -> None:
        """Empty DB returns 200 with null/None values."""
        resp = client.get("/api/weather/today")
        assert resp.status_code == 200


class TestWeatherOutlook:
    def test_weather_outlook_required_keys(self, client: TestClient, db_path: Path) -> None:
        """GET /api/weather/outlook returns Zambretti forecast keys."""
        now = int(time.time())
        conn = sqlite3.connect(str(db_path))
        # Seed pressure history for 3h tendency
        _insert_weather(conn, now - 3 * 3600, pressure_hpa=1015.0)
        _insert_weather(conn, now, pressure_hpa=1013.0)
        conn.commit()
        conn.close()

        resp = client.get("/api/weather/outlook")
        assert resp.status_code == 200
        body = resp.json()
        required_keys = {"verdict", "direction", "based_on_hpa_per_3h", "z_score", "mslp_hpa"}
        for key in required_keys:
            assert key in body, (
                f"'{key}' missing from /api/weather/outlook response; got: {list(body.keys())}"
            )

    def test_weather_outlook_empty_db(self, client: TestClient) -> None:
        """Empty DB returns 200 (graceful empty state)."""
        resp = client.get("/api/weather/outlook")
        assert resp.status_code == 200
