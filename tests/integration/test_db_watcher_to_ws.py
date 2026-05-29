"""Pipeline B: DB-watcher → WebSocket broadcast integration (QA-02).

Boots the real FastAPI app (lifespan-managed db_watcher_loop + run_subscriber),
opens a WS client to /ws, inserts a muon row directly into the tmp SQLite,
and asserts the connected client receives the matching broadcast frame
within ~10s (db_watcher polls every 0.25s under integration_settings).
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_pipeline_b_db_watcher_to_ws(
    integration_settings: None,
    tmp_db_with_migrations: Path,
) -> None:
    # Import after integration_settings rebind so app picks up the test settings.
    from observatory.api.main import app

    muon_ts = int(time.time())

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            # Snapshot-on-connect frame — consume and discard.
            snapshot = ws.receive_json()
            assert snapshot.get("type") == "snapshot"

            # Insert a muon event directly into the tmp DB.
            conn = sqlite3.connect(str(tmp_db_with_migrations))
            try:
                conn.execute(
                    "INSERT INTO muon_events "
                    "(ts, detector_pressure_hpa, detector_temp_c, amplitude, coincidence) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (muon_ts, 1013.0, 20.0, 1.5, 0),
                )
                conn.commit()
            finally:
                conn.close()

            # Drain WS frames until we either see the matching muon broadcast
            # or hit the wall-clock deadline (10s — generous for db_watcher
            # poll @ 0.25s + WS queue fanout).
            deadline = time.time() + 10.0
            saw = False
            while time.time() < deadline:
                # WebSocketTestSession.receive_json blocks; rely on the
                # heartbeat ping or the broadcast frame to wake us. If no
                # frame arrives, the outer deadline will exit the loop.
                try:
                    frame = ws.receive_json()
                except Exception:
                    break
                # Server sends 'ping' frames per api_ws_ping_interval_sec — skip them.
                if frame.get("type") == "ping":
                    continue
                if (
                    frame.get("type") == "muon"
                    and int(frame.get("data", {}).get("ts", -1)) == muon_ts
                ):
                    saw = True
                    break

    assert saw, "WS client did not receive the inserted muon event within 10s"
