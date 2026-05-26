"""Phase 6 — tests for GET /api/stats/today endpoint.

Plan 06-04 TDD RED phase. Tests use a local FastAPI app with the stats
router mounted in isolation.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from observatory.api.routers import stats as stats_router


@pytest.fixture
def client(_ensure_settings_loaded: Path) -> TestClient:
    """Isolated FastAPI app with only the stats router mounted."""
    app = FastAPI()
    app.include_router(stats_router.router, prefix="/api")
    return TestClient(app)


@pytest.fixture
def db_path(_ensure_settings_loaded: Path) -> Path:
    return _ensure_settings_loaded


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_muon(conn: sqlite3.Connection, ts: int) -> None:
    conn.execute(
        "INSERT INTO muon_events (ts, amplitude, coincidence) VALUES (?,?,?)",
        (ts, 100.0, 0),
    )


def _insert_weather(conn: sqlite3.Connection, ts: int, pressure: float = 1013.0) -> None:
    conn.execute(
        "INSERT INTO weather (node_id, ts, pressure_hpa) VALUES (?,?,?)",
        ("enviro", ts, pressure),
    )


def _insert_quake(
    conn: sqlite3.Connection, ts: int, source: str = "usgs", ext_id: str | None = None
) -> None:
    if ext_id is None:
        ext_id = f"{source}_{ts}"
    conn.execute(
        "INSERT INTO earthquakes (source, external_id, ts, magnitude) VALUES (?,?,?,?)",
        (source, ext_id, ts, 3.5),
    )


def _insert_sw(conn: sqlite3.Connection, ts: int, kp_index: float = 2.0) -> None:
    conn.execute(
        "INSERT INTO space_weather (ts, kp_index, flare_class) VALUES (?,?,?)",
        (ts, kp_index, "C1.0"),
    )


def _insert_lightning(conn: sqlite3.Connection, ts: int) -> None:
    conn.execute(
        "INSERT INTO lightning_strikes (ts, latitude, longitude, distance_km) VALUES (?,?,?,?)",
        (ts, 51.5, -0.1, 100.0),
    )


def _insert_aurora(conn: sqlite3.Connection, ts: int) -> None:
    conn.execute(
        "INSERT INTO aurora_status (ts, status, detail) VALUES (?,?,?)",
        (ts, "green", None),
    )


# ---------------------------------------------------------------------------
# Empty DB -> all counts 0, max/min null
# ---------------------------------------------------------------------------


def test_empty_db_all_zeros(client: TestClient) -> None:
    resp = client.get("/api/stats/today")
    assert resp.status_code == 200
    body = resp.json()
    assert body["muon_event_count"] == 0
    assert body["weather_reading_count"] == 0
    assert body["earthquake_count_by_source"] == {"usgs": 0, "emsc": 0, "bgs": 0}
    assert body["space_weather_reading_count"] == 0
    assert body["lightning_strike_count"] == 0
    assert body["aurora_reading_count"] == 0
    assert body["max_muon_rate_per_min"] == 0
    assert body["max_kp_index"] is None
    assert body["max_pressure_hpa"] is None
    assert body["min_pressure_hpa"] is None
    assert "date" in body


# ---------------------------------------------------------------------------
# Seeded data today: counts correct
# ---------------------------------------------------------------------------


def test_seeded_counts(client: TestClient, db_path: Path) -> None:
    now = int(time.time())
    today_start = now - (now % 86400)

    conn = sqlite3.connect(str(db_path))
    # 3 muon events
    for i in range(3):
        _insert_muon(conn, today_start + 60 + i * 10)
    # 2 weather readings
    _insert_weather(conn, today_start + 100, pressure=1010.0)
    _insert_weather(conn, today_start + 200, pressure=1020.0)
    # 1 usgs, 2 emsc earthquakes
    _insert_quake(conn, today_start + 300, source="usgs", ext_id="u1")
    _insert_quake(conn, today_start + 400, source="emsc", ext_id="e1")
    _insert_quake(conn, today_start + 500, source="emsc", ext_id="e2")
    # 4 space weather
    for i in range(4):
        _insert_sw(conn, today_start + 600 + i * 60, kp_index=float(i + 1))
    # 1 lightning
    _insert_lightning(conn, today_start + 700)
    # 5 aurora readings
    for i in range(5):
        _insert_aurora(conn, today_start + 800 + i * 60)
    conn.commit()
    conn.close()

    resp = client.get("/api/stats/today")
    assert resp.status_code == 200
    body = resp.json()
    assert body["muon_event_count"] == 3
    assert body["weather_reading_count"] == 2
    assert body["earthquake_count_by_source"]["usgs"] == 1
    assert body["earthquake_count_by_source"]["emsc"] == 2
    assert body["earthquake_count_by_source"]["bgs"] == 0
    assert body["space_weather_reading_count"] == 4
    assert body["lightning_strike_count"] == 1
    assert body["aurora_reading_count"] == 5


# ---------------------------------------------------------------------------
# max_muon_rate_per_min: 70 events in one minute
# ---------------------------------------------------------------------------


def test_max_muon_rate_per_min(client: TestClient, db_path: Path) -> None:
    now = int(time.time())
    today_start = now - (now % 86400)
    base_minute = today_start + 3600  # 1h into today

    conn = sqlite3.connect(str(db_path))
    # 70 muon events within the same UTC minute
    for i in range(70):
        _insert_muon(conn, base_minute + i % 59)  # all within same minute
    conn.commit()
    conn.close()

    resp = client.get("/api/stats/today")
    body = resp.json()
    assert body["max_muon_rate_per_min"] >= 70


# ---------------------------------------------------------------------------
# UTC boundary: yesterday's data excluded
# ---------------------------------------------------------------------------


def test_utc_boundary_excludes_yesterday(client: TestClient, db_path: Path) -> None:
    now = int(time.time())
    today_start = now - (now % 86400)

    conn = sqlite3.connect(str(db_path))
    # 2 today
    _insert_muon(conn, today_start + 100)
    _insert_muon(conn, today_start + 200)
    # 5 yesterday
    for i in range(5):
        _insert_muon(conn, today_start - 3600 + i * 100)
    conn.commit()
    conn.close()

    resp = client.get("/api/stats/today")
    body = resp.json()
    assert body["muon_event_count"] == 2


# ---------------------------------------------------------------------------
# earthquake_count_by_source always has all 3 keys
# ---------------------------------------------------------------------------


def test_earthquake_count_by_source_always_three_keys(client: TestClient) -> None:
    resp = client.get("/api/stats/today")
    body = resp.json()
    eq_counts = body["earthquake_count_by_source"]
    assert set(eq_counts.keys()) == {"usgs", "emsc", "bgs"}


# ---------------------------------------------------------------------------
# max/min pressure
# ---------------------------------------------------------------------------


def test_max_min_pressure(client: TestClient, db_path: Path) -> None:
    now = int(time.time())
    today_start = now - (now % 86400)

    conn = sqlite3.connect(str(db_path))
    _insert_weather(conn, today_start + 100, pressure=1010.5)
    _insert_weather(conn, today_start + 200, pressure=1023.5)
    _insert_weather(conn, today_start + 300, pressure=1015.0)
    conn.commit()
    conn.close()

    resp = client.get("/api/stats/today")
    body = resp.json()
    assert body["max_pressure_hpa"] == round(1023.5, 2)
    assert body["min_pressure_hpa"] == round(1010.5, 2)


# ---------------------------------------------------------------------------
# max_kp_index
# ---------------------------------------------------------------------------


def test_max_kp_index(client: TestClient, db_path: Path) -> None:
    now = int(time.time())
    today_start = now - (now % 86400)

    conn = sqlite3.connect(str(db_path))
    _insert_sw(conn, today_start + 100, kp_index=2.0)
    _insert_sw(conn, today_start + 200, kp_index=5.33)
    _insert_sw(conn, today_start + 300, kp_index=1.0)
    conn.commit()
    conn.close()

    resp = client.get("/api/stats/today")
    body = resp.json()
    assert body["max_kp_index"] == round(5.33, 2)


# ---------------------------------------------------------------------------
# Response shape
# ---------------------------------------------------------------------------


def test_response_shape(client: TestClient) -> None:
    resp = client.get("/api/stats/today")
    assert resp.status_code == 200
    body = resp.json()
    expected_keys = {
        "date",
        "muon_event_count",
        "weather_reading_count",
        "earthquake_count_by_source",
        "space_weather_reading_count",
        "lightning_strike_count",
        "aurora_reading_count",
        "max_muon_rate_per_min",
        "max_kp_index",
        "max_pressure_hpa",
        "min_pressure_hpa",
    }
    assert set(body.keys()) == expected_keys
