"""Phase 6 — asyncio DB-watcher background task. Implemented by Plan 06-06.

Polls all 6 data tables every settings.api_db_watcher_interval_sec and fans
new rows out to connected WebSocket clients via fanout_event.

Bootstrap: reads MAX(ts) per table at startup so old rows are never replayed
to new connections.

Phase 16 (ENH-01): a tick-counter runs the weekly MIP-peak gain-drift compute
every ``settings.muon_gain_drift_compute_interval_sec`` (default 3600s).
The compute runs in a try/except so a failure never kills the watcher loop.

Import direction: db_watcher.py → ws.py (one-way).
Plan 06-07 wires this into FastAPI lifespan:
    task = asyncio.create_task(db_watcher_loop())
    yield
    task.cancel()
    await task
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import structlog

from observatory.api.routers.ws import fanout_event
from observatory.config import settings
from observatory.db.connection import get_conn

log = structlog.get_logger(__name__)

# Gain-drift tick counter — counts how many watcher sleeps have elapsed since
# the last compute_and_store_weekly_mip_peak call.
_gain_drift_ticks: int = 0

# Alert tick counter — counts watcher sleeps since the last evaluate_rules call.
# Independent of _gain_drift_ticks so the two cadences never interfere.
_alert_ticks: int = 0

# Alert evaluation interval in seconds (evaluate rules once per minute).
ALERT_EVAL_INTERVAL = 60

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
    global _gain_drift_ticks, _alert_ticks
    _gain_drift_ticks = 0
    _alert_ticks = 0
    gain_drift_threshold = max(
        1,
        settings.muon_gain_drift_compute_interval_sec // settings.api_db_watcher_interval_sec,
    )

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

                # Gain-drift MIP-peak compute on configured cadence.
                _gain_drift_ticks += 1
                if _gain_drift_ticks >= gain_drift_threshold:
                    _gain_drift_ticks = 0
                    try:
                        from observatory.muon.gain_drift import (
                            compute_and_store_weekly_mip_peak,
                        )

                        compute_and_store_weekly_mip_peak(conn, int(time.time()))
                        log.debug("gain_drift_computed")
                    except Exception as exc:
                        log.warning("gain_drift_compute_failed", exc=str(exc))

                # Alert rules evaluation — independent cadence (every ~60 s).
                # Separate counter from gain-drift so the two never interfere.
                _alert_ticks += 1
                alert_threshold = max(
                    1, ALERT_EVAL_INTERVAL // settings.api_db_watcher_interval_sec
                )
                if _alert_ticks >= alert_threshold:
                    _alert_ticks = 0
                    try:
                        from observatory.weather.alerts.engine import evaluate_rules

                        evaluate_rules(conn)
                    except Exception as exc:
                        log.warning("alert_eval.failed", error=str(exc))

    except asyncio.CancelledError:
        log.info("db_watcher_cancelled")
        raise  # re-raise for proper lifespan cleanup
