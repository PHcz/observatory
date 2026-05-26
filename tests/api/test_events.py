"""Phase 6 — tests for GET /api/events/recent mixed event feed endpoint.

Plan 06-04 TDD RED phase. Tests use a local FastAPI app with the events
router mounted in isolation.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from observatory.api.routers import events as events_router


@pytest.fixture
def client(_ensure_settings_loaded: Path) -> TestClient:
    """Isolated FastAPI app with only the events router mounted."""
    app = FastAPI()
    app.include_router(events_router.router, prefix="/api")
    return TestClient(app)


@pytest.fixture
def db_path(_ensure_settings_loaded: Path) -> Path:
    return _ensure_settings_loaded


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_weather(conn: sqlite3.Connection, ts: int) -> None:
    conn.execute(
        "INSERT INTO weather (node_id, ts, temp_c, humidity_pct, pressure_hpa) VALUES (?,?,?,?,?)",
        ("enviro", ts, 18.5, 60.0, 1013.0),
    )


def _insert_muon(conn: sqlite3.Connection, ts: int) -> None:
    conn.execute(
        "INSERT INTO muon_events (ts, amplitude, coincidence) VALUES (?,?,?)",
        (ts, 1234.5, 0),
    )


def _insert_quake(conn: sqlite3.Connection, ts: int, ext_id: str = "q1") -> None:
    conn.execute(
        "INSERT INTO earthquakes (source, external_id, ts, magnitude, place) VALUES (?,?,?,?,?)",
        ("usgs", ext_id, ts, 4.5, "Test Place"),
    )


def _insert_sw(conn: sqlite3.Connection, ts: int) -> None:
    conn.execute(
        "INSERT INTO space_weather (ts, kp_index, flare_class) VALUES (?,?,?)",
        (ts, 2.0, "C1.0"),
    )


def _insert_lightning(conn: sqlite3.Connection, ts: int) -> None:
    conn.execute(
        "INSERT INTO lightning_strikes (ts, latitude, longitude, distance_km) VALUES (?,?,?,?)",
        (ts, 51.5, -0.1, 150.0),
    )


def _insert_aurora(conn: sqlite3.Connection, ts: int) -> None:
    conn.execute(
        "INSERT INTO aurora_status (ts, status, detail) VALUES (?,?,?)",
        (ts, "green", None),
    )


# ---------------------------------------------------------------------------
# Empty DB -> rows=[]
# ---------------------------------------------------------------------------


def test_empty_db_returns_empty_rows(client: TestClient) -> None:
    resp = client.get("/api/events/recent")
    assert resp.status_code == 200
    body = resp.json()
    assert body["rows"] == []


# ---------------------------------------------------------------------------
# 1 event per source -> 6 rows with correct type tags
# ---------------------------------------------------------------------------


def test_one_per_source_six_rows(client: TestClient, db_path: Path) -> None:
    now = int(time.time())
    conn = sqlite3.connect(str(db_path))
    _insert_weather(conn, now - 600)
    _insert_muon(conn, now - 500)
    _insert_quake(conn, now - 400)
    _insert_sw(conn, now - 300)
    _insert_lightning(conn, now - 200)
    _insert_aurora(conn, now - 100)
    conn.commit()
    conn.close()

    resp = client.get("/api/events/recent")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["rows"]) == 6
    types = {r["type"] for r in body["rows"]}
    assert types == {"weather", "muon", "earthquake", "space_weather", "lightning", "aurora"}


# ---------------------------------------------------------------------------
# type tags are correct
# ---------------------------------------------------------------------------


def test_each_row_has_type_and_ts_and_data(client: TestClient, db_path: Path) -> None:
    now = int(time.time())
    conn = sqlite3.connect(str(db_path))
    _insert_quake(conn, now - 100)
    conn.commit()
    conn.close()

    resp = client.get("/api/events/recent")
    body = resp.json()
    row = body["rows"][0]
    assert "type" in row
    assert "ts" in row
    assert "data" in row
    assert isinstance(row["data"], dict)  # json.loads was applied


# ---------------------------------------------------------------------------
# Muon cap: 50 muon + 5 quakes -> max 10 muon in response
# ---------------------------------------------------------------------------


def test_muon_cap_enforced(client: TestClient, db_path: Path) -> None:
    now = int(time.time())
    conn = sqlite3.connect(str(db_path))
    # Insert 50 muon events
    for i in range(50):
        _insert_muon(conn, now - 50 + i)
    # Insert 5 earthquakes
    for i in range(5):
        _insert_quake(conn, now - 1000 + i * 10, ext_id=f"q{i}")
    conn.commit()
    conn.close()

    resp = client.get("/api/events/recent")
    body = resp.json()
    muon_rows = [r for r in body["rows"] if r["type"] == "muon"]
    assert len(muon_rows) <= 10


# ---------------------------------------------------------------------------
# Order: latest ts first
# ---------------------------------------------------------------------------


def test_order_latest_first(client: TestClient, db_path: Path) -> None:
    now = int(time.time())
    conn = sqlite3.connect(str(db_path))
    _insert_quake(conn, now - 300, ext_id="q1")
    _insert_quake(conn, now - 100, ext_id="q2")
    _insert_quake(conn, now - 200, ext_id="q3")
    conn.commit()
    conn.close()

    resp = client.get("/api/events/recent")
    body = resp.json()
    tss = [r["ts"] for r in body["rows"]]
    assert tss == sorted(tss, reverse=True)


# ---------------------------------------------------------------------------
# data field is dict (json.loads succeeded), not a JSON string
# ---------------------------------------------------------------------------


def test_data_is_dict_not_string(client: TestClient, db_path: Path) -> None:
    now = int(time.time())
    conn = sqlite3.connect(str(db_path))
    _insert_quake(conn, now - 100)
    conn.commit()
    conn.close()

    resp = client.get("/api/events/recent")
    body = resp.json()
    row = body["rows"][0]
    assert isinstance(row["data"], dict), f"Expected dict, got {type(row['data'])}"
