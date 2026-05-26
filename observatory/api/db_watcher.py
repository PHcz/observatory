"""Phase 6 — asyncio DB-watcher background task. Populated by Plan 06-06."""

from __future__ import annotations


async def db_watcher_loop() -> None:
    """Poll MAX(ts) per data table every settings.api_db_watcher_interval_sec.

    Fan out new rows to connected WS clients.
    """
    raise NotImplementedError("Plan 06-06 implements")
