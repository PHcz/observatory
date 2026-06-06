"""RED integration tests for GET /api/air-quality (Phase 11, OAQ-02).

The air-quality router is created in Wave 2 (plan 11-03). Until then these
requests 404 (route absent) -> the assertions fail RED, which is the expected
Wave-0 state.

Seeds air_quality + air_quality_meta rows in the per-test tmp DB (the autouse
api fixture applies migration 0006), then asserts the cache-serve, empty-state,
and local-first contracts:
  - populated -> 200 with aqi/pollutants/pollen/uv/fetched_at
  - empty tables -> 200 empty-state body (NOT 404)
  - local-first: the router source contains no httpx / no upstream URL (mirror 10-03)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTER_SRC = REPO_ROOT / "observatory" / "api" / "routers" / "air_quality.py"


def _seed(conn: sqlite3.Connection, *, aqi: float = 70.0, fetched_at: int = 1000) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO air_quality "
        "(id, ts, european_aqi, pm2_5, pm10, nitrogen_dioxide, ozone, sulphur_dioxide, "
        "uv_index, alder_pollen, birch_pollen, grass_pollen, mugwort_pollen, olive_pollen, "
        "ragweed_pollen, fetched_at) "
        "VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            1_700_000_000,
            aqi,
            3.7,
            11.2,
            6.1,
            68.0,
            0.4,
            5.5,
            0.0,
            0.0,
            6.7,
            0.0,
            0.0,
            0.0,
            fetched_at,
        ),
    )
    conn.execute(
        "INSERT OR REPLACE INTO air_quality_meta "
        "(id, fetched_at, utc_offset_seconds, timezone) VALUES (1, ?, ?, ?)",
        (fetched_at, 3600, "Europe/London"),
    )


def test_empty_tables_return_empty_state_not_404(api_client: TestClient) -> None:
    r = api_client.get("/api/air-quality")
    assert r.status_code == 200
    body = r.json()
    assert body["aqi"] is None
    assert body["fetched_at"] is None


def test_serves_cached_snapshot(api_client: TestClient, health_db: Path) -> None:
    conn = sqlite3.connect(str(health_db), isolation_level=None)
    try:
        _seed(conn, aqi=70.0, fetched_at=1234)
    finally:
        conn.close()

    body = api_client.get("/api/air-quality").json()
    assert body["aqi"] == 70.0
    assert body["pollutants"]["pm2_5"] == 3.7
    assert body["pollutants"]["pm10"] == 11.2
    assert body["pollutants"]["nitrogen_dioxide"] == 6.1
    assert body["pollutants"]["ozone"] == 68.0
    assert body["pollutants"]["sulphur_dioxide"] == 0.4
    assert body["uv"] == 5.5
    assert body["pollen"]["grass_pollen"] == 6.7
    assert body["fetched_at"] == 1234


def test_router_is_local_first_no_httpx() -> None:
    """The /api/air-quality router must read SQLite only — never call upstream."""
    src = ROUTER_SRC.read_text()
    assert "httpx" not in src
    assert "air-quality-api.open-meteo.com" not in src
