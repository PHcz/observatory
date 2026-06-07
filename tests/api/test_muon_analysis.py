"""RED integration tests for GET /api/muon/analysis (Phase 13, MU2-05).

The muon-analysis route is created in Wave 2 (plan 13-02). Until then these
requests 404 (route absent) -> assertions fail RED, the expected Wave-0 state.

Seeds muon_events rows in the per-test tmp DB (autouse api fixture applies the
schema chain incl 0007), then asserts the compute-on-request contract:
  - populated -> 200 with adc_histogram + barometric (or null) + raw_uncorrected:true
  - empty muon_events -> 200 empty-state (NOT 404)
  - local-first: the router source contains no httpx import (mirror air_quality)
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
# The route may live in muon.py (extend) or a new muon_analysis.py router; the
# local-first grep targets whichever file carries the analysis route. We grep
# both candidates and require at least one to exist and be httpx-free.
ROUTER_CANDIDATES = (
    REPO_ROOT / "observatory" / "api" / "routers" / "muon_analysis.py",
    REPO_ROOT / "observatory" / "api" / "routers" / "muon.py",
)


def _seed_muon(
    conn: sqlite3.Connection, now: int, n_buckets: int = 6, per_bucket: int = 40
) -> None:
    for b in range(n_buckets):
        pressure = 1000.0 + b * 2.0
        base = now - (n_buckets - b) * 3600
        for i in range(per_bucket):
            conn.execute(
                "INSERT INTO muon_events (ts, amplitude, detector_pressure_hpa, coincidence) "
                "VALUES (?, ?, ?, 1)",
                (base + i, 320.0 + (i % 20), pressure),
            )


def test_empty_muon_events_returns_empty_state_not_404(api_client: TestClient) -> None:
    r = api_client.get("/api/muon/analysis")
    assert r.status_code == 200
    body = r.json()
    assert body["adc_histogram"] == []
    assert body["barometric"] is None
    assert body["raw_uncorrected"] is True


def test_serves_analysis_for_populated_window(api_client: TestClient, health_db: Path) -> None:
    now = int(time.time())
    conn = sqlite3.connect(str(health_db), isolation_level=None)
    try:
        _seed_muon(conn, now)
    finally:
        conn.close()

    body = api_client.get("/api/muon/analysis").json()
    assert body["adc_histogram"], "expected ADC histogram bins"
    assert "bin_center" in body["adc_histogram"][0]
    assert "count" in body["adc_histogram"][0]
    assert body["raw_uncorrected"] is True
    # barometric may be a fit dict (real pressure range seeded) or null.
    if body["barometric"] is not None:
        assert "beta" in body["barometric"]
        assert "r_squared" in body["barometric"]


def test_router_is_local_first_no_httpx() -> None:
    existing = [p for p in ROUTER_CANDIDATES if p.exists()]
    assert existing, "no muon-analysis router file found"
    assert any("httpx" not in p.read_text() for p in existing)
