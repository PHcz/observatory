"""Phase 16 ENH-04: GET /api/alerts and alert deduplication.

RED: /api/alerts does not exist and observatory.weather.alerts.engine is not implemented.
This test gates Wave 1 implementation.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from observatory.api.routers import alerts as alerts_router
from observatory.weather.alerts.engine import evaluate_rules


@pytest.fixture
def client(_ensure_settings_loaded: Path) -> TestClient:
    app = FastAPI()
    app.include_router(alerts_router.router, prefix="/api")
    return TestClient(app)


@pytest.fixture
def db_path(_ensure_settings_loaded: Path) -> Path:
    return _ensure_settings_loaded


def test_alerts_endpoint_empty(client: TestClient) -> None:
    """GET /api/alerts on empty DB returns 200 with active and recent lists."""
    resp = client.get("/api/alerts")
    assert resp.status_code == 200
    body = resp.json()
    assert "active" in body, f"'active' missing from /api/alerts response; got: {list(body.keys())}"
    assert "recent" in body, f"'recent' missing from /api/alerts response; got: {list(body.keys())}"
    assert body["active"] == []
    assert isinstance(body["recent"], list)


def test_alert_dedup(db_path: Path) -> None:
    """Evaluating the same frost condition twice inserts only ONE active alert row."""
    conn = sqlite3.connect(str(db_path), isolation_level=None)

    # Seed a frost-triggering weather row
    now = int(time.time())
    # temp=1.0, humidity=95% → dewpoint spread=1.0 < 2.0 → frost triggered
    conn.execute(
        "INSERT INTO weather (node_id, ts, temp_c, humidity_pct, pressure_hpa) "
        "VALUES (?, ?, ?, ?, ?)",
        ("test-node", now, 1.0, 95.0, 1013.0),
    )

    # Evaluate rules twice
    evaluate_rules(conn)
    evaluate_rules(conn)

    # Only ONE active frost_risk row should exist
    rows = conn.execute(
        "SELECT COUNT(*) FROM alerts WHERE rule='frost_risk' AND resolved_at_ts IS NULL"
    ).fetchone()
    assert rows[0] == 1, (
        f"Expected exactly 1 active frost_risk alert after two evaluations, got {rows[0]}"
    )
    conn.close()
