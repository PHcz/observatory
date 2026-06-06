"""Integration tests for GET /api/health.

Exercises the full router against a tmp SQLite DB (seeded per test) with the
Pi thermal layer stubbed via monkeypatching the read_temp_c / read_throttled
imports on the health router module.

All tests assert the CONTEXT-locked nested response shape:
    {status, timestamp, local{weather, muon}, external{6 sources}, pi{...}}
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import observatory.api.routers.health as health_mod

LOCAL_SOURCES = ("weather", "muon")
# Phase 10 FCAST-01 (additive): `forecast` joins the external source set once
# Wave 2 registers it in _freshness + /api/health. RED until then.
# Phase 11 OAQ-02 (additive): `air_quality` joins once Wave 2 registers it.
EXTERNAL_SOURCES = (
    "usgs",
    "emsc",
    "bgs",
    "noaa",
    "blitzortung",
    "aurora",
    "forecast",
    "air_quality",
)


# ---- helpers ----


def _insert_weather(conn: sqlite3.Connection, ts: int) -> None:
    conn.execute(
        "INSERT INTO weather (node_id, ts, temp_c) VALUES (?, ?, ?)",
        ("test-node", ts, 15.0),
    )


def _insert_muon(conn: sqlite3.Connection, ts: int) -> None:
    conn.execute(
        "INSERT INTO muon_events (ts, amplitude, coincidence) VALUES (?, ?, ?)",
        (ts, 1.0, 0),
    )


def _insert_quake(conn: sqlite3.Connection, source: str, ts: int, ext_id: str) -> None:
    conn.execute(
        "INSERT INTO earthquakes (source, external_id, ts, magnitude) VALUES (?, ?, ?, ?)",
        (source, ext_id, ts, 4.5),
    )


def _insert_space_weather(conn: sqlite3.Connection, ts: int) -> None:
    conn.execute("INSERT INTO space_weather (ts, kp_index) VALUES (?, ?)", (ts, 2.0))


def _insert_lightning(conn: sqlite3.Connection, ts: int) -> None:
    conn.execute(
        "INSERT INTO lightning_strikes (ts, latitude, longitude, distance_km) VALUES (?, ?, ?, ?)",
        (ts, 51.5, -0.1, 10.0),
    )


def _insert_aurora(conn: sqlite3.Connection, ts: int) -> None:
    conn.execute("INSERT INTO aurora_status (ts, status) VALUES (?, ?)", (ts, "green"))


def _insert_poller_run(conn: sqlite3.Connection, source: str, ts: int, status: str) -> None:
    conn.execute(
        "INSERT INTO poller_runs (source, started_at, ended_at, status, "
        "events_fetched, events_written) VALUES (?, ?, ?, ?, ?, ?)",
        (source, ts - 1, ts, status, 1, 1),
    )


@pytest.fixture
def stub_thermal(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """Stub thermal reads on the health router. Returns a configurator."""

    def _stub(temp_c: float = 42.1, throttled: str = "0x0", raise_err: bool = False) -> None:
        if raise_err:
            from observatory.pi.thermal import ThermalReadError

            def _raise_temp() -> float:
                raise ThermalReadError("test: vcgencmd missing")

            def _raise_thr() -> str:
                raise ThermalReadError("test: vcgencmd missing")

            monkeypatch.setattr(health_mod, "read_temp_c", _raise_temp)
            monkeypatch.setattr(health_mod, "read_throttled", _raise_thr)
        else:
            monkeypatch.setattr(health_mod, "read_temp_c", lambda: temp_c)
            monkeypatch.setattr(health_mod, "read_throttled", lambda: throttled)

    # Default: friendly happy-path
    _stub()
    return _stub


# ---- shape + happy/empty paths ----


def test_empty_db_all_sources_down(
    api_client: TestClient, stub_thermal: Callable[..., None]
) -> None:
    r = api_client.get("/api/health")
    assert r.status_code == 200
    body = r.json()

    # Top-level keys
    assert set(body.keys()) == {"status", "timestamp", "local", "external", "pi"}
    assert isinstance(body["timestamp"], int)

    # All local sources present with shape. `weather` carries an extra `source`
    # key per CONTEXT.md §specifics (added in 03-04, value=settings.weather_nickname).
    for name in LOCAL_SOURCES:
        s = body["local"][name]
        expected_keys = {
            "last_event_ts",
            "freshness",
            "staleness_threshold_sec",
            "last_poll_status",
            "cadence_warning",
        }
        if name == "weather":
            expected_keys = expected_keys | {"source"}
            assert s["source"] == "observatory-weather"
        assert set(s.keys()) == expected_keys
        assert s["last_event_ts"] is None
        assert s["freshness"] == "down"
        assert s["last_poll_status"] is None

    # All external sources present with shape
    for name in EXTERNAL_SOURCES:
        s = body["external"][name]
        assert set(s.keys()) == {
            "last_event_ts",
            "last_poll_ts",
            "last_poll_status",
            "freshness",
            "staleness_threshold_sec",
            "cadence_warning",
        }
        assert s["last_event_ts"] is None
        assert s["freshness"] == "down"

    assert body["status"] == "down"


def test_populated_db_all_healthy(
    api_client: TestClient,
    health_db: Path,
    stub_thermal: Callable[..., None],
) -> None:
    now = int(time.time())
    conn = sqlite3.connect(str(health_db), isolation_level=None)
    try:
        _insert_weather(conn, now - 30)
        _insert_muon(conn, now - 2)
        _insert_quake(conn, "usgs", now - 30, "u1")
        _insert_quake(conn, "emsc", now - 30, "e1")
        _insert_quake(conn, "bgs", now - 30, "b1")
        _insert_space_weather(conn, now - 30)
        _insert_lightning(conn, now - 10)
        _insert_aurora(conn, now - 30)
        for s in EXTERNAL_SOURCES:
            _insert_poller_run(conn, s, now - 30, "success")
    finally:
        conn.close()

    body = api_client.get("/api/health").json()
    for name in LOCAL_SOURCES:
        assert body["local"][name]["freshness"] == "healthy", name
    for name in EXTERNAL_SOURCES:
        assert body["external"][name]["freshness"] == "healthy", name
    assert body["status"] == "healthy"


# ---- per-source filter for earthquakes ----


def test_earthquake_source_filter_independent_per_source(
    api_client: TestClient,
    health_db: Path,
    stub_thermal: Callable[..., None],
) -> None:
    now = int(time.time())
    conn = sqlite3.connect(str(health_db), isolation_level=None)
    try:
        # usgs healthy (now-60), emsc absent, bgs stale (3700 >= 2*1800 = 3600)
        _insert_quake(conn, "usgs", now - 60, "u1")
        _insert_quake(conn, "bgs", now - 3700, "b1")
        # Recent successful polls for all three so silent-poller rule doesn't trip
        for s in ("usgs", "emsc", "bgs"):
            _insert_poller_run(conn, s, now - 30, "success")
    finally:
        conn.close()

    body = api_client.get("/api/health").json()
    assert body["external"]["usgs"]["freshness"] == "healthy"
    assert body["external"]["bgs"]["freshness"] == "stale"
    # emsc has no events but has a recent successful poll → poller alive,
    # event freshness is "down" (no events) — silent-poller rule does NOT
    # promote (poll is recent), so freshness comes from event age = down.
    assert body["external"]["emsc"]["freshness"] == "down"


# ---- poller_runs cross-check ----


def test_transient_fail_overrides_healthy_event(
    api_client: TestClient,
    health_db: Path,
    stub_thermal: Callable[..., None],
) -> None:
    now = int(time.time())
    conn = sqlite3.connect(str(health_db), isolation_level=None)
    try:
        _insert_quake(conn, "usgs", now - 60, "u1")  # event would be healthy
        _insert_poller_run(conn, "usgs", now - 30, "transient_fail")
    finally:
        conn.close()

    body = api_client.get("/api/health").json()
    assert body["external"]["usgs"]["freshness"] == "down"
    assert body["external"]["usgs"]["last_poll_status"] == "transient_fail"


def test_partial_status_treated_as_healthy(
    api_client: TestClient,
    health_db: Path,
    stub_thermal: Callable[..., None],
) -> None:
    now = int(time.time())
    conn = sqlite3.connect(str(health_db), isolation_level=None)
    try:
        _insert_space_weather(conn, now - 30)
        _insert_poller_run(conn, "noaa", now - 30, "partial")
    finally:
        conn.close()

    body = api_client.get("/api/health").json()
    assert body["external"]["noaa"]["freshness"] == "healthy"
    assert body["external"]["noaa"]["last_poll_status"] == "partial"


# ---- forecast source (Phase 10 FCAST-01, additive — RED until Wave 2) ----


def test_forecast_source_present_in_health(
    api_client: TestClient,
    health_db: Path,
    stub_thermal: Callable[..., None],
) -> None:
    """`forecast` appears in /api/health with freshness derived from
    forecast_meta.fetched_at (NOT MAX(ts) of the 7-day-ahead horizon)."""
    now = int(time.time())
    conn = sqlite3.connect(str(health_db), isolation_level=None)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO forecast_meta "
            "(id, fetched_at, utc_offset_seconds, timezone) VALUES (1, ?, ?, ?)",
            (now - 30, 0, "Europe/London"),
        )
        _insert_poller_run(conn, "forecast", now - 30, "success")
    finally:
        conn.close()

    body = api_client.get("/api/health").json()
    assert "forecast" in body["external"]
    assert body["external"]["forecast"]["freshness"] == "healthy"


# ---- air_quality source (Phase 11 OAQ-02, additive — RED until Wave 2) ----


def test_air_quality_source_present_in_health(
    api_client: TestClient,
    health_db: Path,
    stub_thermal: Callable[..., None],
) -> None:
    """`air_quality` appears in /api/health with freshness derived from
    air_quality_meta.fetched_at (mirrors the forecast freshness anchor)."""
    now = int(time.time())
    conn = sqlite3.connect(str(health_db), isolation_level=None)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO air_quality_meta "
            "(id, fetched_at, utc_offset_seconds, timezone) VALUES (1, ?, ?, ?)",
            (now - 30, 3600, "Europe/London"),
        )
        _insert_poller_run(conn, "air_quality", now - 30, "success")
    finally:
        conn.close()

    body = api_client.get("/api/health").json()
    assert "air_quality" in body["external"]
    assert body["external"]["air_quality"]["freshness"] == "healthy"


# ---- Pi thermal integration ----


def test_pi_thermal_happy_path(api_client: TestClient, stub_thermal: Callable[..., None]) -> None:
    stub_thermal(temp_c=42.1, throttled="0x0")
    body = api_client.get("/api/health").json()
    assert body["pi"]["temp_c"] == 42.1
    assert body["pi"]["throttled"] == "0x0"
    assert body["pi"]["status"] == "healthy"
    assert body["pi"]["warnings"] == []


def test_pi_thermal_warning_escalates_overall_to_stale(
    api_client: TestClient,
    health_db: Path,
    stub_thermal: Callable[..., None],
) -> None:
    # Make all data sources healthy so the pi.status is the only degradation.
    now = int(time.time())
    conn = sqlite3.connect(str(health_db), isolation_level=None)
    try:
        _insert_weather(conn, now - 30)
        _insert_muon(conn, now - 2)
        for s in ("usgs", "emsc", "bgs"):
            _insert_quake(conn, s, now - 30, f"{s}1")
        _insert_space_weather(conn, now - 30)
        _insert_lightning(conn, now - 10)
        _insert_aurora(conn, now - 30)
        for s in EXTERNAL_SOURCES:
            _insert_poller_run(conn, s, now - 30, "success")
    finally:
        conn.close()

    stub_thermal(temp_c=75.0, throttled="0x0")
    body = api_client.get("/api/health").json()
    assert body["pi"]["status"] == "warning"
    assert "pi_temp_high" in body["pi"]["warnings"]
    assert body["status"] == "stale"


def test_pi_thermal_critical_forces_overall_down(
    api_client: TestClient, stub_thermal: Callable[..., None]
) -> None:
    stub_thermal(temp_c=82.0, throttled="0x0")
    body = api_client.get("/api/health").json()
    assert body["pi"]["status"] == "critical"
    assert body["status"] == "down"


def test_pi_thermal_unavailable_does_not_500(
    api_client: TestClient, stub_thermal: Callable[..., None]
) -> None:
    stub_thermal(raise_err=True)
    r = api_client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["pi"]["temp_c"] is None
    assert body["pi"]["throttled"] is None
    # Per orchestrator brief: status="unknown" or graceful "healthy" with warning;
    # plan implementation uses "healthy" with explicit warning so we don't
    # escalate top-level on a tooling issue.
    assert body["pi"]["status"] in {"healthy", "unknown"}
    assert any("thermal" in w for w in body["pi"]["warnings"])
