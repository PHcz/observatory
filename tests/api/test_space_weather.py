"""Phase 6 — tests for GET /api/space-weather time-series endpoint.

Plan 06-03 TDD RED phase. Tests use a local FastAPI app with the space_weather
router mounted in isolation (Plan 06-04 adds /api/space-weather/current).
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from observatory.api.routers import space_weather as sw_router


@pytest.fixture
def client(_ensure_settings_loaded: Path) -> TestClient:
    """Isolated FastAPI app with only the space_weather router mounted."""
    app = FastAPI()
    app.include_router(sw_router.router, prefix="/api")
    return TestClient(app)


@pytest.fixture
def db_path(_ensure_settings_loaded: Path) -> Path:
    return _ensure_settings_loaded


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_sw(
    conn: sqlite3.Connection,
    ts: int,
    kp_index: float = 3.0,
    solar_wind_kms: float = 400.0,
    flare_class: str = "C1.0",
) -> None:
    conn.execute(
        """
        INSERT INTO space_weather (ts, kp_index, solar_wind_kms, flare_class)
        VALUES (?, ?, ?, ?)
        """,
        (ts, kp_index, solar_wind_kms, flare_class),
    )


# ---------------------------------------------------------------------------
# Empty DB
# ---------------------------------------------------------------------------


def test_empty_db_returns_200_with_empty_rows(client: TestClient) -> None:
    resp = client.get("/api/space-weather")
    assert resp.status_code == 200
    body = resp.json()
    assert body["rows"] == []
    assert "window" in body
    assert "bucket_size_sec" in body
    assert "agg" in body


# ---------------------------------------------------------------------------
# Flare class: MAX() picks strongest in bucket
# ---------------------------------------------------------------------------


def test_flare_class_max_picks_strongest(client: TestClient, db_path: Path) -> None:
    """4 rows in one UTC hour bucket — MAX(flare_class) should pick X1.0."""
    import datetime

    now = int(time.time())
    dt_now = datetime.datetime.fromtimestamp(now, tz=datetime.UTC)
    hour_start = dt_now.replace(minute=0, second=0, microsecond=0)
    base = int(hour_start.timestamp()) + 30

    conn = sqlite3.connect(str(db_path))
    _insert_sw(conn, base + 0, flare_class="C1.0")
    _insert_sw(conn, base + 60, flare_class="M2.5")
    _insert_sw(conn, base + 120, flare_class="X1.0")
    _insert_sw(conn, base + 180, flare_class="B5.0")
    conn.commit()
    conn.close()

    from_ts = int(hour_start.timestamp())
    to_ts = from_ts + 3600
    resp = client.get(f"/api/space-weather?from={from_ts}&to={to_ts}&agg=hour")
    assert resp.status_code == 200
    body = resp.json()
    assert body["agg"] == "hour"
    assert len(body["rows"]) == 1
    assert body["rows"][0]["flare_class"] == "X1.0"


# ---------------------------------------------------------------------------
# Raw mode returns all rows with original flare_class
# ---------------------------------------------------------------------------


def test_raw_mode_returns_all_rows(client: TestClient, db_path: Path) -> None:
    """Short window -> auto=raw; all 4 rows returned with original flare_class."""
    now = int(time.time())
    conn = sqlite3.connect(str(db_path))
    classes = ["C1.0", "M2.5", "X1.0", "B5.0"]
    for i, fc in enumerate(classes):
        _insert_sw(conn, now - 3600 + i * 60, flare_class=fc)
    conn.commit()
    conn.close()

    # Short enough window (< 2h but covering our rows)
    from_ts = now - 3600
    resp = client.get(f"/api/space-weather?from={from_ts}&to={now}&agg=raw")
    assert resp.status_code == 200
    body = resp.json()
    assert body["agg"] == "raw"
    assert len(body["rows"]) == 4
    returned_classes = {row["flare_class"] for row in body["rows"]}
    assert returned_classes == set(classes)


# ---------------------------------------------------------------------------
# kp_index averaging
# ---------------------------------------------------------------------------


def test_kp_index_averaging(client: TestClient, db_path: Path) -> None:
    """Two rows with kp=2.0 and kp=4.0 in same hour bucket -> AVG = 3.0."""
    # Use a fixed epoch that starts at an exact UTC hour boundary + a few seconds,
    # so both rows (+0s and +120s) land in the same UTC hour bucket regardless of
    # when this test runs.
    import datetime

    now = int(time.time())
    # Align base to the start of the current UTC hour + 30s so both rows are safely inside.
    dt_now = datetime.datetime.fromtimestamp(now, tz=datetime.UTC)
    hour_start = dt_now.replace(minute=0, second=0, microsecond=0)
    base = int(hour_start.timestamp()) + 30  # 30s past the hour

    conn = sqlite3.connect(str(db_path))
    _insert_sw(conn, base, kp_index=2.0, solar_wind_kms=350.0)
    _insert_sw(conn, base + 120, kp_index=4.0, solar_wind_kms=450.0)
    conn.commit()
    conn.close()

    # Query the full current UTC hour
    from_ts = int(hour_start.timestamp())
    to_ts = from_ts + 3600
    resp = client.get(f"/api/space-weather?from={from_ts}&to={to_ts}&agg=hour")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["rows"]) == 1
    row = body["rows"][0]
    assert abs(row["kp_index"] - 3.0) < 0.01
    assert abs(row["solar_wind_kms"] - 400.0) < 0.1


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------


def test_from_gt_to_returns_422(client: TestClient) -> None:
    resp = client.get("/api/space-weather?from=2000&to=1000")
    assert resp.status_code == 422


def test_invalid_agg_returns_422(client: TestClient) -> None:
    resp = client.get("/api/space-weather?agg=bogus")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Response shape
# ---------------------------------------------------------------------------


def test_response_shape(client: TestClient) -> None:
    resp = client.get("/api/space-weather")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"window", "bucket_size_sec", "agg", "rows"}
    assert set(body["window"].keys()) == {"from", "to"}


# ---------------------------------------------------------------------------
# /api/space-weather/current (Plan 06-04 addition)
# ---------------------------------------------------------------------------


def test_current_empty_db_returns_404(client: TestClient) -> None:
    resp = client.get("/api/space-weather/current")
    assert resp.status_code == 404


def test_current_returns_latest_row_by_ts(client: TestClient, db_path: Path) -> None:
    now = int(time.time())
    conn = sqlite3.connect(str(db_path))
    _insert_sw(conn, now - 300, kp_index=1.0, solar_wind_kms=350.0, flare_class="B1.0")
    _insert_sw(conn, now - 100, kp_index=5.0, solar_wind_kms=600.0, flare_class="X2.1")  # latest
    _insert_sw(conn, now - 200, kp_index=2.0, solar_wind_kms=400.0, flare_class="C1.0")
    conn.commit()
    conn.close()

    resp = client.get("/api/space-weather/current")
    assert resp.status_code == 200
    body = resp.json()
    assert body["kp_index"] == round(5.0, 2)
    assert body["ts"] == now - 100
    assert body["flare_class"] == "X2.1"


def test_current_response_shape(client: TestClient, db_path: Path) -> None:
    now = int(time.time())
    conn = sqlite3.connect(str(db_path))
    _insert_sw(conn, now - 100)
    conn.commit()
    conn.close()

    resp = client.get("/api/space-weather/current")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"ts", "kp_index", "solar_wind_kms", "flare_class", "flare_peak_ts"}


def test_current_rounding(client: TestClient, db_path: Path) -> None:
    now = int(time.time())
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO space_weather (ts, kp_index, solar_wind_kms, flare_class) VALUES (?,?,?,?)",
        (now - 50, 3.789, 412.345, "C3.1"),
    )
    conn.commit()
    conn.close()

    resp = client.get("/api/space-weather/current")
    body = resp.json()
    assert body["kp_index"] == round(3.789, 2)
    assert body["solar_wind_kms"] == round(412.345, 1)
