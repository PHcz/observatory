"""Phase 6 — /ws WebSocket endpoint. Populated by Plan 06-06."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    raise NotImplementedError("Plan 06-06 implements")
