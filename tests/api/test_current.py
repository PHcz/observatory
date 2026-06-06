"""Phase 6 — tests for GET /api/current snapshot endpoint.

Plan 06-05 TDD. Tests use a local FastAPI app with only the current router mounted.
Uses the autouse `_ensure_settings_loaded` fixture from conftest.py.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from observatory.api.routers import current as cur_router


@pytest.fixture
def client(_ensure_settings_loaded: Path) -> TestClient:
    """Isolated FastAPI app with only the current router mounted."""
    app = FastAPI()
    app.include_router(cur_router.router, prefix="/api")
    return TestClient(app)


@pytest.fixture
def db_path(_ensure_settings_loaded: Path) -> Path:
    return _ensure_settings_loaded


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_weather(
    conn: sqlite3.Connection,
    ts: int,
    temp_c: float = 20.0,
    humidity_pct: float = 60.0,
    pressure_hpa: float = 1013.0,
    lux: float = 500.0,
) -> None:
    conn.execute(
        "INSERT INTO weather"
        " (node_id, ts, temp_c, humidity_pct, pressure_hpa, lux, battery_v, wifi_rssi)"
        " VALUES ('outdoor', ?, ?, ?, ?, ?, NULL, NULL)",
        (ts, temp_c, humidity_pct, pressure_hpa, lux),
    )


def _insert_muon(
    conn: sqlite3.Connection,
    ts: int,
    amplitude: float = 1.0,
    coincidence: int = 0,
    detector_pressure_hpa: float = 1010.0,
    detector_temp_c: float = 22.0,
) -> None:
    conn.execute(
        "INSERT INTO muon_events"
        " (ts, amplitude, coincidence, detector_pressure_hpa, detector_temp_c)"
        " VALUES (?, ?, ?, ?, ?)",
        (ts, amplitude, coincidence, detector_pressure_hpa, detector_temp_c),
    )


def _insert_space_weather(
    conn: sqlite3.Connection,
    ts: int,
    kp_index: float = 2.0,
    solar_wind_kms: float = 400.0,
    flare_class: str = "C1.0",
) -> None:
    conn.execute(
        "INSERT INTO space_weather (ts, kp_index, solar_wind_kms, flare_class, flare_peak_ts)"
        " VALUES (?, ?, ?, ?, NULL)",
        (ts, kp_index, solar_wind_kms, flare_class),
    )


def _insert_lightning(
    conn: sqlite3.Connection,
    ts: int,
    distance_km: float = 100.0,
    latitude: float = 51.5,
    longitude: float = -0.1,
) -> None:
    conn.execute(
        "INSERT INTO lightning_strikes (ts, latitude, longitude, distance_km) VALUES (?, ?, ?, ?)",
        (ts, latitude, longitude, distance_km),
    )


def _insert_aurora(
    conn: sqlite3.Connection,
    ts: int,
    status: str = "green",
    detail: str = "Low activity",
) -> None:
    conn.execute(
        "INSERT INTO aurora_status (ts, status, detail) VALUES (?, ?, ?)",
        (ts, status, detail),
    )


def _insert_earthquake(
    conn: sqlite3.Connection,
    ts: int,
    source: str = "usgs",
    external_id: str | None = None,
    magnitude: float = 4.5,
    place: str = "Test location",
    depth_km: float = 10.0,
    latitude: float = 35.0,
    longitude: float = 139.0,
) -> None:
    if external_id is None:
        external_id = f"{source}-{ts}"
    conn.execute(
        "INSERT INTO earthquakes"
        " (source, external_id, ts, magnitude, depth_km, latitude, longitude, place)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (source, external_id, ts, magnitude, depth_km, latitude, longitude, place),
    )


def _insert_poller_run(
    conn: sqlite3.Connection,
    source: str,
    status: str,
    ended_at: int,
) -> None:
    conn.execute(
        "INSERT INTO poller_runs (source, status, ended_at, started_at) VALUES (?, ?, ?, ?)",
        (source, status, ended_at, ended_at - 5),
    )


# ---------------------------------------------------------------------------
# Empty DB — basic shape + all-down freshness
# ---------------------------------------------------------------------------


def test_empty_db_status_200(client: TestClient) -> None:
    resp = client.get("/api/current")
    assert resp.status_code == 200


def test_empty_db_top_level_keys(client: TestClient) -> None:
    resp = client.get("/api/current")
    body = resp.json()
    assert set(body.keys()) == {
        "timestamp",
        "astronomy",
        "weather",
        "muon",
        "space_weather",
        "lightning_summary",
        "aurora",
        "earthquakes_recent",
    }


def test_empty_db_astronomy_keys(client: TestClient) -> None:
    resp = client.get("/api/current")
    body = resp.json()
    assert set(body["astronomy"].keys()) == {
        "sunrise_ts",
        "sunset_ts",
        "moon_phase",
        "moon_illumination_pct",
        "moonrise_ts",
        "moonset_ts",
    }


def test_empty_db_source_blocks_down(client: TestClient) -> None:
    resp = client.get("/api/current")
    body = resp.json()
    for key in ("weather", "muon", "space_weather", "aurora"):
        assert body[key]["freshness"] == "down", f"{key}.freshness should be down on empty DB"
        assert body[key]["data"] is None, f"{key}.data should be None on empty DB"


def test_empty_db_lightning_summary_freshness_down(client: TestClient) -> None:
    resp = client.get("/api/current")
    body = resp.json()
    assert body["lightning_summary"]["freshness"] == "down"
    # lightning_summary.data is always non-null (well-defined aggregate)
    assert body["lightning_summary"]["data"] is not None
    data = body["lightning_summary"]["data"]
    assert data["past_hour"] == 0
    assert data["past_24h"] == 0
    assert data["nearest_km"] is None
    assert data["total_today"] == 0


def test_empty_db_earthquakes_recent_empty(client: TestClient) -> None:
    resp = client.get("/api/current")
    body = resp.json()
    assert body["earthquakes_recent"] == []


# ---------------------------------------------------------------------------
# Weather freshness transitions
# ---------------------------------------------------------------------------


def test_weather_healthy(client: TestClient, db_path: Path) -> None:
    now = int(time.time())
    conn = sqlite3.connect(str(db_path))
    _insert_weather(conn, now - 60)  # age 60 < 2*900=1800 -> healthy
    conn.commit()
    conn.close()

    resp = client.get("/api/current")
    body = resp.json()
    assert body["weather"]["freshness"] == "healthy"
    assert body["weather"]["data"] is not None
    assert body["weather"]["data"]["temp_c"] == pytest.approx(20.0, abs=0.01)


def test_weather_stale(client: TestClient, db_path: Path) -> None:
    now = int(time.time())
    conn = sqlite3.connect(str(db_path))
    _insert_weather(conn, now - 1900)  # age 1900 >= 2*900=1800, < 4*900=3600 -> stale
    conn.commit()
    conn.close()

    resp = client.get("/api/current")
    body = resp.json()
    assert body["weather"]["freshness"] == "stale"


def test_weather_down(client: TestClient, db_path: Path) -> None:
    now = int(time.time())
    conn = sqlite3.connect(str(db_path))
    _insert_weather(conn, now - 3700)  # age 3700 >= 4*900=3600 -> down
    conn.commit()
    conn.close()

    resp = client.get("/api/current")
    body = resp.json()
    assert body["weather"]["freshness"] == "down"


# ---------------------------------------------------------------------------
# Muon block
# ---------------------------------------------------------------------------


def test_muon_rate_per_min_within_window(client: TestClient, db_path: Path) -> None:
    now = int(time.time())
    conn = sqlite3.connect(str(db_path))
    # Insert 65 events within last 60s
    for i in range(65):
        _insert_muon(conn, now - 50 + i % 30)
    conn.commit()
    conn.close()

    resp = client.get("/api/current")
    body = resp.json()
    assert body["muon"]["data"] is not None
    assert body["muon"]["data"]["rate_per_min"] == 65


def test_muon_rate_per_min_outside_window(client: TestClient, db_path: Path) -> None:
    now = int(time.time())
    conn = sqlite3.connect(str(db_path))
    # Insert events outside 60s window
    for i in range(5):
        _insert_muon(conn, now - 120 - i * 10)
    conn.commit()
    conn.close()

    resp = client.get("/api/current")
    body = resp.json()
    assert body["muon"]["data"] is not None
    assert body["muon"]["data"]["rate_per_min"] == 0
    assert body["muon"]["data"]["latest_event_ts"] is not None


# ---------------------------------------------------------------------------
# Earthquakes — LIMIT 5 + multi-source ordering
# ---------------------------------------------------------------------------


def test_earthquakes_recent_limit_5(client: TestClient, db_path: Path) -> None:
    now = int(time.time())
    conn = sqlite3.connect(str(db_path))
    for i in range(10):
        _insert_earthquake(conn, now - i * 60, source="usgs", external_id=f"usgs-{i}")
    conn.commit()
    conn.close()

    resp = client.get("/api/current")
    body = resp.json()
    assert len(body["earthquakes_recent"]) == 5
    # Should be ordered DESC by ts (most recent first)
    tss = [e["ts"] for e in body["earthquakes_recent"]]
    assert tss == sorted(tss, reverse=True)


def test_earthquakes_recent_cross_source(client: TestClient, db_path: Path) -> None:
    now = int(time.time())
    conn = sqlite3.connect(str(db_path))
    # 2 USGS, 2 EMSC, 1 BGS at varied ts
    _insert_earthquake(conn, now - 100, source="usgs", external_id="u1")
    _insert_earthquake(conn, now - 200, source="usgs", external_id="u2")
    _insert_earthquake(conn, now - 300, source="emsc", external_id="e1")
    _insert_earthquake(conn, now - 400, source="emsc", external_id="e2")
    _insert_earthquake(conn, now - 500, source="bgs", external_id="b1")
    conn.commit()
    conn.close()

    resp = client.get("/api/current")
    body = resp.json()
    eq = body["earthquakes_recent"]
    assert len(eq) == 5
    sources = {e["source"] for e in eq}
    assert "usgs" in sources
    assert "emsc" in sources
    assert "bgs" in sources


def test_earthquakes_recent_shape(client: TestClient, db_path: Path) -> None:
    now = int(time.time())
    conn = sqlite3.connect(str(db_path))
    _insert_earthquake(conn, now - 100)
    conn.commit()
    conn.close()

    resp = client.get("/api/current")
    body = resp.json()
    eq = body["earthquakes_recent"][0]
    assert set(eq.keys()) == {"ts", "source", "magnitude", "place", "depth_km"}


# ---------------------------------------------------------------------------
# Astronomy sanity
# ---------------------------------------------------------------------------


def test_astronomy_sunrise_before_sunset(client: TestClient) -> None:
    resp = client.get("/api/current")
    body = resp.json()
    ast = body["astronomy"]
    # London lat — sunrise < sunset on normal day
    assert ast["sunrise_ts"] < ast["sunset_ts"]


def test_astronomy_moon_illumination_range(client: TestClient) -> None:
    resp = client.get("/api/current")
    body = resp.json()
    illum = body["astronomy"]["moon_illumination_pct"]
    assert 0.0 <= illum <= 100.0


def test_astronomy_moon_phase_range(client: TestClient) -> None:
    resp = client.get("/api/current")
    body = resp.json()
    phase = body["astronomy"]["moon_phase"]
    assert 0.0 <= phase < 1.0


# ---------------------------------------------------------------------------
# Poller cross-check: transient_fail forces freshness down
# ---------------------------------------------------------------------------


def test_lightning_poller_transient_fail_forces_down(client: TestClient, db_path: Path) -> None:
    """A healthy lightning row + recent transient_fail poller run -> freshness=down."""
    now = int(time.time())
    conn = sqlite3.connect(str(db_path))
    # Recent lightning strike (would be healthy on its own)
    _insert_lightning(conn, now - 10, distance_km=100.0)
    # transient_fail poller run very recent
    _insert_poller_run(conn, "blitzortung", "transient_fail", now - 10)
    conn.commit()
    conn.close()

    resp = client.get("/api/current")
    body = resp.json()
    assert body["lightning_summary"]["freshness"] == "down"


# ---------------------------------------------------------------------------
# build_current_snapshot direct call (exported for Plan 06-06)
# ---------------------------------------------------------------------------


def test_build_current_snapshot_direct_call(db_path: Path) -> None:
    """Direct call to build_current_snapshot returns the expected dict shape."""
    from observatory.api.routers.current import build_current_snapshot
    from observatory.db.connection import get_conn

    with get_conn() as conn:
        result = build_current_snapshot(conn)

    assert isinstance(result, dict)
    assert set(result.keys()) == {
        "timestamp",
        "astronomy",
        "weather",
        "muon",
        "space_weather",
        "lightning_summary",
        "aurora",
        "earthquakes_recent",
    }


def test_build_current_snapshot_callable() -> None:
    """build_current_snapshot is a module-level callable (importable by Plan 06-06)."""
    from observatory.api.routers.current import build_current_snapshot

    assert callable(build_current_snapshot)
