"""Phase 6 — /ws WebSocket endpoint with per-client Queue + heartbeat + fanout.

Implemented by Plan 06-06.

Module-level state:
  connected_clients: dict[client_id, ClientState] — protected by ws_lock.
  ws_lock: asyncio.Lock — must be held for all reads/writes to connected_clients.

Import direction: db_watcher.py → ws.py (one-way).
Plan 06-07 wires db_watcher_loop into FastAPI lifespan.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from observatory.api.routers.current import build_current_snapshot
from observatory.config import settings
from observatory.db.connection import get_conn

log = structlog.get_logger(__name__)

router = APIRouter()


@dataclass
class ClientState:
    """Per-client connection state."""

    client_id: str
    queue: asyncio.Queue  # type: ignore[type-arg]  # asyncio.Queue[dict[str, Any]]
    last_pong_ts: float = field(default_factory=time.time)  # epoch float for sub-second tests


# Module-level registry — protected by ws_lock.
# Tests must call connected_clients.clear() between test runs.
connected_clients: dict[str, ClientState] = {}
ws_lock: asyncio.Lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# fanout_event — exported for db_watcher
# ---------------------------------------------------------------------------


async def fanout_event(envelope: dict[str, Any]) -> None:
    """Put envelope on every connected client's queue; drop-oldest on full.

    Acquires ws_lock briefly to snapshot client IDs, then enqueues without lock.
    On QueueFull: drops the oldest item, logs WARNING event=ws_queue_full_dropped_oldest.

    Args:
        envelope: Dict with keys 'type', 'data', 'ts'.
    """
    async with ws_lock:
        client_ids = list(connected_clients.keys())  # snapshot — avoid mutation during fan-out

    for cid in client_ids:
        # Re-fetch state without lock — may be None if client disconnected mid-fan-out
        state = connected_clients.get(cid)
        if state is None:
            continue
        try:
            state.queue.put_nowait(envelope)
        except asyncio.QueueFull:
            # Drop oldest then enqueue newest
            try:
                state.queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                state.queue.put_nowait(envelope)
            except asyncio.QueueFull:
                pass  # Shouldn't happen post-drop; ignore
            log.warning("ws_queue_full_dropped_oldest", client_id=cid)


# ---------------------------------------------------------------------------
# /ws endpoint
# ---------------------------------------------------------------------------


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    """WebSocket endpoint for live dashboard updates.

    On connect:
      1. Accepts the connection.
      2. Sends a snapshot frame immediately.
      3. Runs three concurrent loops (send, recv, heartbeat) via asyncio.gather.

    On disconnect (any cause):
      - Removes client from connected_clients registry.
      - Logs INFO event=ws_client_disconnected.

    Heartbeat:
      - Server pings every settings.api_ws_ping_interval_sec.
      - Server drops client if no pong within settings.api_ws_pong_timeout_sec.
    """
    await ws.accept()

    client_id = str(uuid.uuid4())[:8]
    state = ClientState(
        client_id=client_id,
        queue=asyncio.Queue(maxsize=settings.api_ws_queue_maxsize),
        last_pong_ts=time.time(),
    )

    async with ws_lock:
        connected_clients[client_id] = state

    log.info(
        "ws_client_connected",
        client_id=client_id,
        total_clients=len(connected_clients),
    )

    # --- Snapshot on connect ---
    with get_conn() as conn:
        snapshot = build_current_snapshot(conn)
    await ws.send_json({"type": "snapshot", "data": snapshot, "ts": int(time.time())})

    # --- Three concurrent coroutines ---
    # We use asyncio.gather with return_exceptions=True so that when one loop
    # raises WebSocketDisconnect (or returns on heartbeat timeout), the gather
    # call returns. We then cancel the remaining tasks explicitly.
    #
    # Pattern: each loop signals disconnect via a shared Event rather than raising,
    # so gather completes naturally without hanging.

    _done = asyncio.Event()

    async def send_loop() -> None:
        """Drain the per-client queue and send to WebSocket."""
        while not _done.is_set():
            try:
                msg = await asyncio.wait_for(state.queue.get(), timeout=0.5)
            except TimeoutError:
                continue
            if _done.is_set():
                return
            try:
                await ws.send_json(msg)
            except WebSocketDisconnect:
                _done.set()
                return

    async def recv_loop() -> None:
        """Receive inbound messages; handle pong; ignore others."""
        try:
            while True:
                msg = await ws.receive_json()
                if msg.get("type") == "pong":
                    state.last_pong_ts = time.time()
                else:
                    log.info(
                        "ws_client_message_ignored",
                        client_id=client_id,
                        msg_type=msg.get("type"),
                    )
        except WebSocketDisconnect:
            _done.set()

    async def heartbeat_loop() -> None:
        """Send ping at interval; drop client if no pong within timeout."""
        while not _done.is_set():
            await asyncio.sleep(settings.api_ws_ping_interval_sec)
            if _done.is_set():
                return
            try:
                await ws.send_json({"type": "ping", "ts": int(time.time())})
            except WebSocketDisconnect:
                _done.set()
                return
            if time.time() - state.last_pong_ts > settings.api_ws_pong_timeout_sec:
                log.info(
                    "ws_client_disconnected_no_pong",
                    client_id=client_id,
                )
                _done.set()
                try:
                    await ws.close()
                except Exception:
                    pass
                return

    try:
        await asyncio.gather(
            send_loop(),
            recv_loop(),
            heartbeat_loop(),
            return_exceptions=True,
        )
    except WebSocketDisconnect:
        pass
    finally:
        async with ws_lock:
            connected_clients.pop(client_id, None)
        log.info(
            "ws_client_disconnected",
            client_id=client_id,
            total_clients=len(connected_clients),
        )
