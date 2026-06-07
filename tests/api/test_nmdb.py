"""RED integration tests for GET /api/nmdb (Phase 13, MU2-06).

The nmdb router is created in Wave 3 (plan 13-04). Until then these requests 404
(route absent) -> assertions fail RED, the expected Wave-0 state.

Seeds nmdb_counts + nmdb_meta (and muon_events for the local %-baseline) in the
per-test tmp DB, then asserts:
  - populated -> 200 with series (counts + pct_baseline) + local + fetched_at
  - empty tables -> 200 empty-state (NOT 404)
  - local-first: the router source contains no httpx import
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTER_SRC = REPO_ROOT / "observatory" / "api" / "routers" / "nmdb.py"


def _seed_nmdb(conn: sqlite3.Connection, now: int, fetched_at: int = 1234) -> None:
    for i in range(24):
        conn.execute(
            "INSERT OR IGNORE INTO nmdb_counts (station, ts, counts_per_sec) VALUES (?, ?, ?)",
            ("OULU", now - (24 - i) * 3600, 100.0 + (i % 5)),
        )
    conn.execute(
        "INSERT OR REPLACE INTO nmdb_meta (id, fetched_at, station) VALUES (1, ?, ?)",
        (fetched_at, "OULU"),
    )


def test_empty_tables_return_empty_state_not_404(api_client: TestClient) -> None:
    r = api_client.get("/api/nmdb")
    assert r.status_code == 200
    body = r.json()
    assert body["series"] == []
    assert body["fetched_at"] is None


def test_serves_series_with_pct_baseline(api_client: TestClient, health_db: Path) -> None:
    now = int(time.time())
    conn = sqlite3.connect(str(health_db), isolation_level=None)
    try:
        _seed_nmdb(conn, now, fetched_at=4242)
    finally:
        conn.close()

    body = api_client.get("/api/nmdb").json()
    assert body["series"], "expected NMDB series"
    point = body["series"][0]
    assert "ts" in point
    assert "counts_per_sec" in point
    assert "pct_baseline" in point
    assert body["fetched_at"] == 4242
    assert "local" in body


def test_router_is_local_first_no_httpx() -> None:
    src = ROUTER_SRC.read_text()
    assert "httpx" not in src
    assert "nmdb.eu" not in src
