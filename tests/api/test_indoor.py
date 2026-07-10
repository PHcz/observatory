"""Phase 15 — GET /api/indoor/current + /api/indoor/history."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from fastapi.testclient import TestClient


def _insert(
    db: Path,
    node: str,
    ts: int,
    co2: int,
    temp: float = 21.0,
    hum: float = 40.0,
    pres: float = 1015.0,
) -> None:
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO indoor_air (node_id, ts, temp_c, humidity_pct, pressure_hpa, co2_ppm) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (node, ts, temp, hum, pres, co2),
    )
    conn.commit()
    conn.close()


class TestIndoorCurrent:
    def test_empty_returns_empty_nodes(self, api_client: TestClient) -> None:
        r = api_client.get("/api/indoor/current")
        assert r.status_code == 200
        assert r.json()["nodes"] == []

    def test_latest_row_per_node(self, api_client: TestClient, health_db: Path) -> None:
        now = int(time.time())
        _insert(health_db, "living-room", now - 120, 800)
        _insert(health_db, "living-room", now - 60, 820)  # newer → wins
        _insert(health_db, "bedroom", now - 30, 600)
        r = api_client.get("/api/indoor/current")
        nodes = {n["node_id"]: n for n in r.json()["nodes"]}
        assert nodes["living-room"]["co2_ppm"] == 820
        assert nodes["bedroom"]["co2_ppm"] == 600
        assert nodes["living-room"]["age_sec"] >= 60


class TestIndoorHistory:
    def test_empty_returns_empty_rows(self, api_client: TestClient) -> None:
        r = api_client.get("/api/indoor/history")
        assert r.status_code == 200
        assert r.json()["rows"] == []

    def test_window_and_node_filter(self, api_client: TestClient, health_db: Path) -> None:
        now = int(time.time())
        _insert(health_db, "living-room", now - 3600, 700)  # in 24h window
        _insert(health_db, "living-room", now - 30 * 3600, 500)  # 30h ago → excluded
        _insert(health_db, "bedroom", now - 1800, 600)  # filtered out by node param
        r = api_client.get("/api/indoor/history?hours=24&node=living-room")
        rows = r.json()["rows"]
        assert all(row["node_id"] == "living-room" for row in rows)
        co2s = {row["co2_ppm"] for row in rows}
        assert 700 in co2s
        assert 500 not in co2s  # outside 24h window
        assert 600 not in co2s  # other node

    def test_hours_bounds_validated(self, api_client: TestClient) -> None:
        assert api_client.get("/api/indoor/history?hours=0").status_code == 422
        assert api_client.get("/api/indoor/history?hours=999").status_code == 422
