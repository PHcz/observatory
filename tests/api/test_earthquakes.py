"""Phase 6 — tests for GET /api/earthquakes paginated list endpoint.

Plan 06-04 TDD RED phase. Tests use a local FastAPI app with the earthquakes
router mounted in isolation.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from observatory.api.routers import earthquakes as eq_router


@pytest.fixture
def client(_ensure_settings_loaded: Path) -> TestClient:
    """Isolated FastAPI app with only the earthquakes router mounted."""
    app = FastAPI()
    app.include_router(eq_router.router, prefix="/api")
    return TestClient(app)


@pytest.fixture
def db_path(_ensure_settings_loaded: Path) -> Path:
    return _ensure_settings_loaded


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_quake(
    conn: sqlite3.Connection,
    ts: int,
    source: str = "usgs",
    external_id: str | None = None,
    magnitude: float = 3.5,
    depth_km: float = 10.0,
    latitude: float = 35.0,
    longitude: float = -120.0,
    place: str = "Test Location",
) -> None:
    if external_id is None:
        external_id = f"{source}_{ts}"
    conn.execute(
        """
        INSERT INTO earthquakes (source, external_id, ts, magnitude, depth_km,
                                  latitude, longitude, place)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (source, external_id, ts, magnitude, depth_km, latitude, longitude, place),
    )


# ---------------------------------------------------------------------------
# Empty DB
# ---------------------------------------------------------------------------


def test_empty_db_returns_200_empty_rows(client: TestClient) -> None:
    resp = client.get("/api/earthquakes")
    assert resp.status_code == 200
    body = resp.json()
    assert body["rows"] == []
    assert body["next_before_ts"] is None
    assert "window" in body
    assert "limit" in body


# ---------------------------------------------------------------------------
# Pagination: 150 rows, default limit=100
# ---------------------------------------------------------------------------


def test_pagination_first_page(client: TestClient, db_path: Path) -> None:
    """150 earthquakes, default limit=100 -> first page has 100 rows + cursor."""
    now = int(time.time())
    conn = sqlite3.connect(str(db_path))
    for i in range(150):
        ts = now - 86400 + i * 576  # spread over ~24h
        _insert_quake(conn, ts, external_id=f"eq_{i}")
    conn.commit()
    conn.close()

    resp = client.get("/api/earthquakes")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["rows"]) == 100
    # Page is full -> next_before_ts must be set
    assert body["next_before_ts"] is not None
    # Rows should be ordered DESC by ts
    tss = [r["ts"] for r in body["rows"]]
    assert tss == sorted(tss, reverse=True)


def test_pagination_second_page(client: TestClient, db_path: Path) -> None:
    """Second page returns remaining 50 rows + null cursor."""
    now = int(time.time())
    conn = sqlite3.connect(str(db_path))
    for i in range(150):
        ts = now - 86400 + i * 576
        _insert_quake(conn, ts, external_id=f"eq_{i}")
    conn.commit()
    conn.close()

    # Get first page
    resp1 = client.get("/api/earthquakes")
    body1 = resp1.json()
    cursor = body1["next_before_ts"]
    assert cursor is not None

    # Get second page using cursor
    resp2 = client.get(f"/api/earthquakes?before_ts={cursor}")
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert len(body2["rows"]) == 50
    assert body2["next_before_ts"] is None


# ---------------------------------------------------------------------------
# min_mag filter
# ---------------------------------------------------------------------------


def test_min_mag_filter(client: TestClient, db_path: Path) -> None:
    now = int(time.time())
    conn = sqlite3.connect(str(db_path))
    _insert_quake(conn, now - 100, magnitude=2.0, external_id="small")
    _insert_quake(conn, now - 200, magnitude=5.5, external_id="big")
    _insert_quake(conn, now - 300, magnitude=3.0, external_id="medium")
    conn.commit()
    conn.close()

    resp = client.get("/api/earthquakes?min_mag=5.0")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["rows"]) == 1
    assert body["rows"][0]["magnitude"] >= 5.0


# ---------------------------------------------------------------------------
# Validation: over MAX_LIMIT + zero limit
# ---------------------------------------------------------------------------


def test_limit_over_max_returns_422(client: TestClient) -> None:
    resp = client.get("/api/earthquakes?limit=2000")
    assert resp.status_code == 422


def test_limit_zero_returns_422(client: TestClient) -> None:
    resp = client.get("/api/earthquakes?limit=0")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Multi-source: source field present in rows
# ---------------------------------------------------------------------------


def test_multi_source_rows(client: TestClient, db_path: Path) -> None:
    now = int(time.time())
    conn = sqlite3.connect(str(db_path))
    _insert_quake(conn, now - 100, source="usgs", external_id="u1")
    _insert_quake(conn, now - 200, source="emsc", external_id="e1")
    _insert_quake(conn, now - 300, source="bgs", external_id="b1")
    conn.commit()
    conn.close()

    resp = client.get("/api/earthquakes")
    assert resp.status_code == 200
    body = resp.json()
    sources = {r["source"] for r in body["rows"]}
    assert sources == {"usgs", "emsc", "bgs"}


# ---------------------------------------------------------------------------
# Row shape
# ---------------------------------------------------------------------------


def test_row_shape(client: TestClient, db_path: Path) -> None:
    now = int(time.time())
    conn = sqlite3.connect(str(db_path))
    _insert_quake(conn, now - 100, external_id="shape_test")
    conn.commit()
    conn.close()

    resp = client.get("/api/earthquakes")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["rows"]) == 1
    row = body["rows"][0]
    expected_keys = {
        "ts",
        "source",
        "external_id",
        "magnitude",
        "depth_km",
        "latitude",
        "longitude",
        "place",
    }
    assert set(row.keys()) == expected_keys
