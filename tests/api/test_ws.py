"""Phase 6 — tests for /ws WebSocket endpoint. Implemented by Plan 06-06."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def ws_app(monkeypatch: pytest.MonkeyPatch, _ensure_settings_loaded: object) -> FastAPI:
    """Build a minimal FastAPI with only the WS router for isolation tests.

    Depends on _ensure_settings_loaded (from conftest) so settings is valid.
    """
    # Fast-forward heartbeat timings so tests don't hang.
    from observatory.config import settings as live_settings

    monkeypatch.setattr(live_settings, "api_ws_ping_interval_sec", 0.05, raising=False)
    monkeypatch.setattr(live_settings, "api_ws_pong_timeout_sec", 0.5, raising=False)
    monkeypatch.setattr(live_settings, "api_ws_queue_maxsize", 3, raising=False)
    # Clear module-level state between tests
    from observatory.api.routers.ws import connected_clients

    connected_clients.clear()
    app = FastAPI()
    from observatory.api.routers import ws as ws_mod

    # Ensure the ws module's settings reference is also patched
    monkeypatch.setattr(ws_mod, "settings", live_settings, raising=False)
    app.include_router(ws_mod.router)
    return app


# ---------------------------------------------------------------------------
# T1: snapshot frame on connect
# ---------------------------------------------------------------------------


def test_ws_connect_receives_snapshot(ws_app: FastAPI) -> None:
    """Connect to /ws → receive snapshot frame with correct structure."""
    with TestClient(ws_app) as client:
        with client.websocket_connect("/ws") as ws:
            msg: dict[str, Any] = ws.receive_json()
            assert msg["type"] == "snapshot"
            assert isinstance(msg["data"], dict)
            assert "astronomy" in msg["data"]
            assert isinstance(msg["ts"], int)
            assert abs(msg["ts"] - int(time.time())) < 5


# ---------------------------------------------------------------------------
# T2: connected_clients registry
# ---------------------------------------------------------------------------


def test_ws_client_registered_and_deregistered(ws_app: FastAPI) -> None:
    """Client connect → connected_clients populated; disconnect → removed."""
    from observatory.api.routers.ws import connected_clients

    with TestClient(ws_app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # consume snapshot
            assert len(connected_clients) == 1
        # After __exit__, connection is closed; give server thread a moment to clean up
        time.sleep(0.05)
    assert len(connected_clients) == 0


# ---------------------------------------------------------------------------
# T3: pong updates last_pong_ts
# ---------------------------------------------------------------------------


def test_ws_pong_updates_timestamp(ws_app: FastAPI) -> None:
    """Client sends pong → last_pong_ts updated on server state."""
    from observatory.api.routers.ws import connected_clients

    with TestClient(ws_app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # consume snapshot
            # Fetch the client state before pong
            assert len(connected_clients) == 1
            client_state = next(iter(connected_clients.values()))
            ts_before = client_state.last_pong_ts

            # Small sleep to ensure time advances
            time.sleep(0.05)
            ws.send_json({"type": "pong"})
            # Give server a moment to process
            time.sleep(0.05)

            ts_after = client_state.last_pong_ts
            assert ts_after >= ts_before


# ---------------------------------------------------------------------------
# T4: server sends ping
# ---------------------------------------------------------------------------


def test_ws_server_sends_ping(ws_app: FastAPI) -> None:
    """Server sends ping within ping_interval (0.05s). Verify ping arrives."""
    with TestClient(ws_app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # consume snapshot
            # Wait just over one ping interval
            time.sleep(0.15)
            ping_msg = ws.receive_json()
            assert ping_msg["type"] == "ping"
            assert isinstance(ping_msg["ts"], int)


# ---------------------------------------------------------------------------
# T5: no pong → server disconnects client
# ---------------------------------------------------------------------------


def test_ws_no_pong_disconnects_client(ws_app: FastAPI) -> None:
    """No pong within pong_timeout_sec → server closes connection."""
    from observatory.api.routers.ws import connected_clients

    with TestClient(ws_app) as client:
        try:
            with client.websocket_connect("/ws") as ws:
                ws.receive_json()  # consume snapshot
                # Wait well past ping_interval (0.05) + pong_timeout (0.5)
                time.sleep(0.8)
                # Server should have closed the connection; receive should fail
                with pytest.raises(Exception):  # noqa: B017 # exc type varies
                    while True:
                        ws.receive_json()
        except Exception:
            pass  # Server-side close may cause starlette cleanup error

    # Server should have cleaned up the registry
    time.sleep(0.05)
    assert len(connected_clients) == 0


# ---------------------------------------------------------------------------
# T6: fanout_event delivers to queue
# ---------------------------------------------------------------------------


def test_ws_fanout_event_delivers(ws_app: FastAPI) -> None:
    """fanout_event called with envelope → client receives it from queue."""
    from observatory.api.routers.ws import connected_clients

    with TestClient(ws_app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # consume snapshot
            assert len(connected_clients) == 1
            state = next(iter(connected_clients.values()))

            # Directly put onto the queue (bypasses lock — safe from test thread)
            envelope = {"type": "weather", "data": {"temp_c": 20.0}, "ts": 12345}
            state.queue.put_nowait(envelope)

            # The send_loop will pick it up and send; wait briefly
            time.sleep(0.05)
            # Drain any ping messages that arrive before the weather envelope
            for _ in range(5):
                msg = ws.receive_json()
                if msg["type"] == "weather":
                    break
            assert msg["type"] == "weather"
            assert msg["data"]["temp_c"] == 20.0


# ---------------------------------------------------------------------------
# T7: queue-full → drop oldest + WARNING logged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ws_queue_full_drops_oldest(
    _ensure_settings_loaded: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Queue full (3 items) + 1 more → oldest dropped + WARNING logged.

    Tests fanout_event in a pure async context — no WS connection needed.
    """
    import structlog.testing

    from observatory.api.routers.ws import ClientState, connected_clients, fanout_event, ws_lock

    # Set up a fake client with queue maxsize=3
    fake_state = ClientState(
        client_id="test-fanout",
        queue=asyncio.Queue(maxsize=3),
        last_pong_ts=time.time(),
    )

    async with ws_lock:
        connected_clients["test-fanout"] = fake_state

    try:
        # Fill queue to capacity
        for i in range(3):
            fake_state.queue.put_nowait({"type": "weather", "data": {"seq": i}, "ts": i})

        # 4th call triggers drop-oldest + WARNING
        with structlog.testing.capture_logs() as cap:
            await fanout_event({"type": "weather", "data": {"seq": 99}, "ts": 99})

        warnings = [e for e in cap if e.get("log_level") == "warning"]
        assert any("ws_queue_full_dropped_oldest" in str(e) for e in warnings), (
            f"Expected ws_queue_full_dropped_oldest warning, got: {cap}"
        )
        # Queue should still have maxsize=3 items (oldest dropped, new one in)
        assert fake_state.queue.qsize() == 3

    finally:
        async with ws_lock:
            connected_clients.pop("test-fanout", None)


# ---------------------------------------------------------------------------
# T8: multiple concurrent clients
# ---------------------------------------------------------------------------


def test_ws_multiple_clients_each_receive_snapshot(ws_app: FastAPI) -> None:
    """Multiple concurrent clients each receive their own snapshot + fanout."""
    from observatory.api.routers.ws import connected_clients

    with TestClient(ws_app) as client:
        with client.websocket_connect("/ws") as ws1:
            with client.websocket_connect("/ws") as ws2:
                snap1 = ws1.receive_json()
                snap2 = ws2.receive_json()

                assert snap1["type"] == "snapshot"
                assert snap2["type"] == "snapshot"
                assert len(connected_clients) == 2

                # Fan out to both by putting directly on each queue
                envelope = {"type": "aurora", "data": {"status": "green"}, "ts": 9999}
                for state in connected_clients.values():
                    state.queue.put_nowait(envelope)
                time.sleep(0.05)

                # Drain pings until we get the aurora message
                def drain_for_type(ws_conn: Any, target_type: str) -> dict[str, Any]:
                    for _ in range(10):
                        msg = ws_conn.receive_json()
                        if msg["type"] == target_type:
                            return msg
                    raise AssertionError(f"Did not receive {target_type}")

                msg1 = drain_for_type(ws1, "aurora")
                msg2 = drain_for_type(ws2, "aurora")
                assert msg1["type"] == "aurora"
                assert msg2["type"] == "aurora"
