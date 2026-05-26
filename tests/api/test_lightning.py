"""Phase 6 — tests for GET /api/lightning/summary endpoint.

Plan 06-04 TDD RED phase. Tests use a local FastAPI app with the lightning
router mounted in isolation.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from observatory.api.routers import lightning as lt_router


@pytest.fixture
def client(_ensure_settings_loaded: Path) -> TestClient:
    """Isolated FastAPI app with only the lightning router mounted."""
    app = FastAPI()
    app.include_router(lt_router.router, prefix="/api")
    return TestClient(app)


@pytest.fixture
def db_path(_ensure_settings_loaded: Path) -> Path:
    return _ensure_settings_loaded


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_strike(
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


# ---------------------------------------------------------------------------
# Empty DB
# ---------------------------------------------------------------------------


def test_empty_db_returns_zero_counts(client: TestClient) -> None:
    resp = client.get("/api/lightning/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["past_hour"] == 0
    assert body["past_24h"] == 0
    assert body["nearest_km"] is None
    assert body["total_today"] == 0
    assert "ts" in body


# ---------------------------------------------------------------------------
# past_hour + past_24h counts
# ---------------------------------------------------------------------------


def test_hour_and_24h_counts(client: TestClient, db_path: Path) -> None:
    now = int(time.time())
    conn = sqlite3.connect(str(db_path))
    # 5 strikes in last hour
    for i in range(5):
        _insert_strike(conn, now - 1800 + i * 60)
    # 3 more strikes: >1h ago but <24h ago
    for i in range(3):
        _insert_strike(conn, now - 7200 + i * 100)
    conn.commit()
    conn.close()

    resp = client.get("/api/lightning/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["past_hour"] == 5
    assert body["past_24h"] == 8


# ---------------------------------------------------------------------------
# nearest_km = minimum distance in last 24h
# ---------------------------------------------------------------------------


def test_nearest_km(client: TestClient, db_path: Path) -> None:
    now = int(time.time())
    conn = sqlite3.connect(str(db_path))
    _insert_strike(conn, now - 100, distance_km=100.0)
    _insert_strike(conn, now - 200, distance_km=50.0)
    _insert_strike(conn, now - 300, distance_km=10.0)
    conn.commit()
    conn.close()

    resp = client.get("/api/lightning/summary")
    body = resp.json()
    assert body["nearest_km"] == 10.0


def test_nearest_km_rounds_to_1dp(client: TestClient, db_path: Path) -> None:
    now = int(time.time())
    conn = sqlite3.connect(str(db_path))
    _insert_strike(conn, now - 100, distance_km=10.123456)
    conn.commit()
    conn.close()

    resp = client.get("/api/lightning/summary")
    body = resp.json()
    assert body["nearest_km"] == round(10.123456, 1)


# ---------------------------------------------------------------------------
# total_today: UTC boundary — yesterday excluded
# ---------------------------------------------------------------------------


def test_total_today_excludes_yesterday(client: TestClient, db_path: Path) -> None:
    now = int(time.time())
    today_start = now - (now % 86400)  # start of UTC day

    conn = sqlite3.connect(str(db_path))
    # 4 strikes today
    for i in range(4):
        _insert_strike(conn, today_start + 60 + i * 100)
    # 3 strikes yesterday (before today_start)
    for i in range(3):
        _insert_strike(conn, today_start - 3600 + i * 100)
    conn.commit()
    conn.close()

    resp = client.get("/api/lightning/summary")
    body = resp.json()
    assert body["total_today"] == 4


# ---------------------------------------------------------------------------
# Response shape
# ---------------------------------------------------------------------------


def test_response_shape(client: TestClient) -> None:
    resp = client.get("/api/lightning/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"past_hour", "past_24h", "nearest_km", "total_today", "ts"}
