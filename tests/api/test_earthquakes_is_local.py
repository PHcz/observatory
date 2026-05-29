"""Phase 8.5 UI-18: /api/earthquakes surfaces is_local on every row.

Inserts two rows directly (one is_local=1, one is_local=0), then asserts the
JSON response carries the field with the correct boolean/0-1 value on both.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from observatory.api.routers import earthquakes as eq_router


@pytest.fixture
def client(_ensure_settings_loaded: Path) -> TestClient:
    app = FastAPI()
    app.include_router(eq_router.router, prefix="/api")
    return TestClient(app)


@pytest.fixture
def db_path(_ensure_settings_loaded: Path) -> Path:
    return _ensure_settings_loaded


def test_is_local_field_present_on_each_row(client: TestClient, db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO earthquakes (source, external_id, ts, magnitude, depth_km, "
            "latitude, longitude, place, is_local) "
            "VALUES ('bgs', 'bgs_local_1', 1700000000, 2.5, 5.0, 51.0, -1.0, 'UK', 1)"
        )
        conn.execute(
            "INSERT INTO earthquakes (source, external_id, ts, magnitude, depth_km, "
            "latitude, longitude, place, is_local) "
            "VALUES ('usgs', 'usgs_remote_1', 1700000001, 5.0, 10.0, 0.0, 0.0, 'X', 0)"
        )
        conn.commit()
    finally:
        conn.close()

    resp = client.get("/api/earthquakes?from=0&to=2000000000&min_mag=0.0&limit=50")
    assert resp.status_code == 200, resp.text
    rows = resp.json()["rows"]
    assert len(rows) == 2
    for row in rows:
        assert "is_local" in row, f"row missing is_local: {row}"

    by_id = {r["external_id"]: r for r in rows}
    # Stored as INTEGER 0/1; either boolean-coerced or 0/1 surfaced — both acceptable
    # per plan. Just assert truthiness matches the seeded value.
    assert bool(by_id["bgs_local_1"]["is_local"]) is True
    assert bool(by_id["usgs_remote_1"]["is_local"]) is False
