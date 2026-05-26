"""Phase 6 — asyncio DB-watcher background task. Implemented by Plan 06-06.

Polls all 6 data tables every settings.api_db_watcher_interval_sec and fans
new rows out to connected WebSocket clients via fanout_event.

Bootstrap: reads MAX(ts) per table at startup so old rows are never replayed
to new connections.

Import direction: db_watcher.py → ws.py (one-way).
Plan 06-07 wires this into FastAPI lifespan:
    task = asyncio.create_task(db_watcher_loop())
    yield
    task.cancel()
    await task
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from observatory.api.routers.ws import fanout_event
from observatory.config import settings
from observatory.db.connection import get_conn

log = structlog.get_logger(__name__)

# Table name → WebSocket event type name.
# Keys are whitelisted here; no user input reaches the SQL f-strings below.
TABLE_EVENT_TYPES: dict[str, str] = {
    "weather": "weather",
    "muon_events": "muon",
    "earthquakes": "earthquake",
    "space_weather": "space_weather",
    "lightning_strikes": "lightning",
    "aurora_status": "aurora",
}

# Maximum rows emitted per table per tick (prevents burst-replay of large back-fills).
PER_TICK_LIMIT = 100


async def db_watcher_loop() -> None:
    """Poll 6 data tables, fan out new rows to connected WS clients.

    Lifecycle:
      1. Bootstrap: reads MAX(ts) per table — old rows are silently ignored.
      2. Main loop: every api_db_watcher_interval_sec, queries each table for
         rows newer than last_seen, fans them out as typed envelopes.
      3. Cancellation: re-raises asyncio.CancelledError for lifespan cleanup.
    """
    # ------------------------------------------------------------------
    # Step 1: Bootstrap — read MAX(ts) per table so old rows don't replay
    # ------------------------------------------------------------------
    with get_conn() as conn:
        last_seen: dict[str, int] = {
            tbl: int(
                conn.execute(
                    f"SELECT COALESCE(MAX(ts), 0) FROM {tbl}"  # nosec B608 — tbl is from whitelist
                ).fetchone()[0]
            )
            for tbl in TABLE_EVENT_TYPES
        }
    log.info("db_watcher_started", last_seen=last_seen)

    # ------------------------------------------------------------------
    # Step 2: Main poll loop
    # ------------------------------------------------------------------
    try:
        while True:
            await asyncio.sleep(settings.api_db_watcher_interval_sec)

            with get_conn() as conn:
                for tbl, evt_type in TABLE_EVENT_TYPES.items():
                    rows: list[Any] = conn.execute(
                        f"SELECT * FROM {tbl} WHERE ts > ? ORDER BY ts ASC LIMIT ?",  # nosec B608
                        (last_seen[tbl], PER_TICK_LIMIT),
                    ).fetchall()
                    for row in rows:
                        envelope: dict[str, Any] = {
                            "type": evt_type,
                            "data": dict(row),
                            "ts": int(row["ts"]),
                        }
                        await fanout_event(envelope)
                    if rows:
                        last_seen[tbl] = int(rows[-1]["ts"])

    except asyncio.CancelledError:
        log.info("db_watcher_cancelled")
        raise  # re-raise for proper lifespan cleanup
