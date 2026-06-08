"""Phase 16 ENH-01: /api/muon returns flux_cm2_min and effective_area_cm2.

RED: the /api/muon route does not yet return these fields.
This test gates Wave 1 implementation.
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
    app = FastAPI()
    app.include_router(muon_router.router, prefix="/api")
    return TestClient(app)


@pytest.fixture
def db_path(_ensure_settings_loaded: Path) -> Path:
    return _ensure_settings_loaded


def _insert_muon(conn: sqlite3.Connection, ts: int, amplitude: float = 0.5) -> None:
    conn.execute(
        "INSERT INTO muon_events "
        "(ts, detector_pressure_hpa, detector_temp_c, amplitude, coincidence) "
        "VALUES (?, ?, ?, ?, ?)",
        (ts, 1013.0, 20.0, amplitude, 1),
    )


def test_muon_flux_fields_present(client: TestClient, db_path: Path) -> None:
    """Bucketed /api/muon response must include flux_cm2_min and effective_area_cm2."""
    now = int(time.time())
    conn = sqlite3.connect(str(db_path))
    # Seed 60 events spread over 1 hour to force bucketed response
    for i in range(60):
        _insert_muon(conn, now - 3600 + i * 60)
    conn.commit()
    conn.close()

    from_ts = now - 3600
    resp = client.get(f"/api/muon?from={from_ts}&to={now}&agg=minute")
    assert resp.status_code == 200
    body = resp.json()
    rows = body.get("rows", [])
    assert len(rows) > 0, "Expected bucketed rows"
    row = rows[0]
    assert "flux_cm2_min" in row, f"flux_cm2_min missing from bucketed muon row: {row.keys()}"
    assert "effective_area_cm2" in row, (
        f"effective_area_cm2 missing from bucketed muon row: {row.keys()}"
    )


def test_muon_flux_value_correct(client: TestClient, db_path: Path) -> None:
    """flux_cm2_min == round(rate_per_min / effective_area_cm2, 4)."""
    now = int(time.time())
    conn = sqlite3.connect(str(db_path))
    # 10 events in exactly 60s → rate_per_min = 10.0; with area=25.0 → flux=0.4
    for i in range(10):
        _insert_muon(conn, now - 60 + i * 6)
    conn.commit()
    conn.close()

    from_ts = now - 120
    resp = client.get(f"/api/muon?from={from_ts}&to={now}&agg=minute")
    assert resp.status_code == 200
    body = resp.json()
    rows = body.get("rows", [])
    assert len(rows) > 0
    for row in rows:
        if row.get("event_count", 0) > 0:
            area = row["effective_area_cm2"]
            rate = row["rate_per_min"]
            expected_flux = round(rate / area, 4)
            assert row["flux_cm2_min"] == pytest.approx(expected_flux, abs=0.0001)
