"""RED integration tests for GET /api/forbush (Phase 13, MU2-07).

The forbush router is created in Wave 4 (plan 13-05). Until then these requests
404 (route absent) -> assertions fail RED, the expected Wave-0 state.

Asserts the state-machine-output contract:
  - empty DB (no NMDB) -> 200 Quiet with the locked detail line (NOT 404)
  - populated -> 200 with state + inputs (nmdb_drop_pct, kp, solar_wind_kms, local_drop_pct)
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
ROUTER_SRC = REPO_ROOT / "observatory" / "api" / "routers" / "forbush.py"


def test_empty_db_returns_quiet_empty_state_not_404(api_client: TestClient) -> None:
    r = api_client.get("/api/forbush")
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "quiet"
    assert "Awaiting neutron-monitor data" in body["detail"]


def test_returns_state_and_inputs(api_client: TestClient, health_db: Path) -> None:
    now = int(time.time())
    conn = sqlite3.connect(str(health_db), isolation_level=None)
    try:
        # Stable NMDB baseline + recent dip; plus a quiet space-weather row.
        for i in range(24):
            conn.execute(
                "INSERT OR IGNORE INTO nmdb_counts (station, ts, counts_per_sec) VALUES (?, ?, ?)",
                ("OULU", now - (24 - i) * 3600, 100.0),
            )
        conn.execute(
            "INSERT OR REPLACE INTO nmdb_meta (id, fetched_at, station) VALUES (1, ?, ?)",
            (now, "OULU"),
        )
        conn.execute(
            "INSERT INTO space_weather (ts, kp_index, solar_wind_kms) VALUES (?, ?, ?)",
            (now - 1800, 2.0, 380.0),
        )
    finally:
        conn.close()

    body = api_client.get("/api/forbush").json()
    assert body["state"] in {"quiet", "watch", "forbush"}
    for key in ("nmdb_drop_pct", "kp", "solar_wind_kms", "local_drop_pct", "detail"):
        assert key in body


def test_router_is_local_first_no_httpx() -> None:
    src = ROUTER_SRC.read_text()
    assert "httpx" not in src
