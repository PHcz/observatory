"""Phase 6 — tests for GET /api/muon time-series endpoint.

Plan 06-03 TDD RED phase. Tests use a local FastAPI app with the muon router
mounted in isolation.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from observatory.api.routers import muon as muon_router


@pytest.fixture
def client(_ensure_settings_loaded: Path) -> TestClient:
    """Isolated FastAPI app with only the muon router mounted."""
    app = FastAPI()
    app.include_router(muon_router.router, prefix="/api")
    return TestClient(app)


@pytest.fixture
def db_path(_ensure_settings_loaded: Path) -> Path:
    return _ensure_settings_loaded


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_muon(conn: sqlite3.Connection, ts: int, **kwargs: object) -> None:
    conn.execute(
        """
        INSERT INTO muon_events (ts, detector_pressure_hpa, detector_temp_c, amplitude, coincidence)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            ts,
            kwargs.get("detector_pressure_hpa", 1013.0),
            kwargs.get("detector_temp_c", 20.0),
            kwargs.get("amplitude", 0.5),
            kwargs.get("coincidence", 0),
        ),
    )


# ---------------------------------------------------------------------------
# Empty DB
# ---------------------------------------------------------------------------


def test_empty_db_returns_200_with_empty_rows(client: TestClient) -> None:
    resp = client.get("/api/muon")
    assert resp.status_code == 200
    body = resp.json()
    assert body["rows"] == []
    assert "window" in body
    assert "bucket_size_sec" in body
    assert "agg" in body


# ---------------------------------------------------------------------------
# Raw rows (short window -> auto=raw)
# ---------------------------------------------------------------------------


def test_short_window_raw_rows(client: TestClient, db_path: Path) -> None:
    """60s window -> auto=raw; 60 seeded events all return."""
    now = int(time.time())
    conn = sqlite3.connect(str(db_path))
    for i in range(60):
        _insert_muon(conn, now - i, coincidence=i % 2)
    conn.commit()
    conn.close()

    from_ts = now - 60
    resp = client.get(f"/api/muon?from={from_ts}&to={now}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["agg"] == "raw"
    assert len(body["rows"]) == 60
    # Raw rows must NOT have rate_per_min
    for row in body["rows"]:
        assert "rate_per_min" not in row
        # coincidence must be integer
        assert isinstance(row["coincidence"], int)


# ---------------------------------------------------------------------------
# Minute-bucketed with rate_per_min
# ---------------------------------------------------------------------------


def test_minute_bucketed_has_rate_per_min(client: TestClient, db_path: Path) -> None:
    """600 events over 1h with agg=minute -> 60 buckets, each 10 events -> rate_per_min=10."""
    now = int(time.time())
    conn = sqlite3.connect(str(db_path))
    # Spread 600 events evenly over 3600 seconds (10 per minute bucket)
    for i in range(600):
        _insert_muon(conn, now - 3600 + i * 6)  # every 6 seconds = 10 per minute
    conn.commit()
    conn.close()

    from_ts = now - 3600
    resp = client.get(f"/api/muon?from={from_ts}&to={now}&agg=minute")
    assert resp.status_code == 200
    body = resp.json()
    assert body["agg"] == "minute"
    rows = body["rows"]
    assert len(rows) > 0
    row0 = rows[0]
    # Bucketed rows must have rate_per_min and event_count
    assert "rate_per_min" in row0
    assert "event_count" in row0
    # rate_per_min for 10 events/minute = 10.0
    # Use a middle bucket to avoid boundary effects (first/last buckets may be partial).
    # At least one interior bucket should have exactly 10 events.
    event_counts = [r["event_count"] for r in rows]
    assert max(event_counts) >= 9  # interior buckets have ≥9 events per minute


# ---------------------------------------------------------------------------
# agg=hour for 24h window
# ---------------------------------------------------------------------------


def test_agg_hour_returns_few_rows(client: TestClient, db_path: Path) -> None:
    now = int(time.time())
    conn = sqlite3.connect(str(db_path))
    for i in range(100):
        _insert_muon(conn, now - i * 900)  # every 15 min
    conn.commit()
    conn.close()

    from_ts = now - 86400
    resp = client.get(f"/api/muon?from={from_ts}&to={now}&agg=hour")
    assert resp.status_code == 200
    body = resp.json()
    assert body["agg"] == "hour"
    assert len(body["rows"]) <= 25


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


def test_from_gt_to_returns_422(client: TestClient) -> None:
    resp = client.get("/api/muon?from=2000&to=1000")
    assert resp.status_code == 422


def test_invalid_agg_returns_422(client: TestClient) -> None:
    resp = client.get("/api/muon?agg=invalid")
    assert resp.status_code == 422
