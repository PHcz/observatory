"""Dedup-aware writer + separate-transaction poller_runs emit + parse-outcome helper.

Two transactions (events INSERT, then poller_runs INSERT) so the audit
row survives any event-write rollback (CONTEXT Open Question 4 / Pitfall 10).
"""

from __future__ import annotations

import sqlite3
import time

import structlog

from observatory.config import settings
from observatory.db.connection import get_write_conn
from observatory.pollers._types import EarthquakeEvent

log = structlog.get_logger(__name__)


def compute_parse_outcome(
    good: int,
    failures: int,
    threshold: float | None = None,
) -> tuple[str, str | None]:
    """Decide poller exit status from per-item parse results.

    Implements the CONTEXT-locked partial-parse contract:
      - 10 fetched, 8 parse cleanly -> ('success', None); caller writes the 8
      - failure ratio EXCEEDS threshold -> ('parse_fail', summary); caller writes 0

    Boundary semantics: ratio == threshold is NOT a failure (CONTEXT
    wording is "exceeds 50%", strict greater-than).
    Empty fetch (good == failures == 0) is success — legitimate quiet period.

    Returns (status, error_summary). Summary is None on success, else a
    short human-readable string e.g. 'parse_fail_ratio=0.80 (8/10)'.
    """
    if threshold is None:
        threshold = settings.poller_parse_failure_threshold
    total = good + failures
    if total == 0:
        return ("success", None)
    ratio = failures / total
    if ratio > threshold:
        summary = f"parse_fail_ratio={ratio:.2f} ({failures}/{total})"
        return ("parse_fail", summary)
    return ("success", None)


def write_events(
    source: str,
    events: list[EarthquakeEvent],
    started_at: int,
    status: str,
    error_summary: str | None = None,
) -> tuple[int, int]:
    """Write events with INSERT OR IGNORE and emit one poller_runs row.

    Uses TWO transactions so the audit row lands even if the events
    transaction rolls back (Pitfall 10 in 04-RESEARCH).

    Returns (fetched, written).
    """
    fetched = len(events)
    written = 0
    events_status = status
    events_error = error_summary

    # --- Transaction 1: event inserts (best-effort) ---
    if events:
        try:
            with get_write_conn() as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    for ev in events:
                        cur = conn.execute(
                            "INSERT OR IGNORE INTO earthquakes "
                            "(source, external_id, ts, magnitude, depth_km, "
                            "latitude, longitude, place) "
                            "VALUES (?,?,?,?,?,?,?,?)",
                            (
                                ev.source,
                                ev.external_id,
                                ev.ts,
                                ev.magnitude,
                                ev.depth_km,
                                ev.latitude,
                                ev.longitude,
                                ev.place,
                            ),
                        )
                        written += cur.rowcount  # 1 on insert, 0 on ignore (dedup)
                    conn.execute("COMMIT")
                except Exception:
                    conn.execute("ROLLBACK")
                    raise
        except (sqlite3.Error, sqlite3.ProgrammingError, sqlite3.InterfaceError) as exc:
            events_status = "db_fail"
            events_error = f"{type(exc).__name__}: {exc}"
            written = 0
            log.error("write_events_db_failure", source=source, error=str(exc))

    # --- Transaction 2: audit row (always attempted) ---
    ended_at = int(time.time())
    try:
        with get_write_conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT INTO poller_runs "
                "(source, started_at, ended_at, status, events_fetched, "
                "events_written, error_summary) VALUES (?,?,?,?,?,?,?)",
                (
                    source,
                    started_at,
                    ended_at,
                    events_status,
                    fetched,
                    written,
                    events_error[:200] if events_error else None,
                ),
            )
            conn.execute("COMMIT")
    except sqlite3.Error as exc:
        log.error("poller_runs_emit_failed", source=source, error=str(exc))

    if events and written < fetched and events_status == "success":
        log.info(
            "dedup_skipped",
            source=source,
            skipped=fetched - written,
            fetched=fetched,
            written=written,
        )
    return fetched, written
