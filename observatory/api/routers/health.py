"""GET /api/health — operational status across all sources + Pi thermal.

Reads MAX(ts) from each data table (earthquakes filtered by source) and
the latest poller_runs row per external source, then derives per-source
freshness via the pure-function layer in observatory.api._freshness.

Pi thermal is read per request via observatory.pi.thermal helpers; if vcgencmd
is unavailable (dev Mac, container, missing binary) we surface temp_c=None and
a "pi_thermal_unavailable" warning but do NOT escalate the overall status —
the operator can read the warning, but the health probe itself stays useful.

Response shape locked in 05-CONTEXT.md §"/api/health response shape".
"""

from __future__ import annotations

import sqlite3
import time
from typing import Any

import structlog
from fastapi import APIRouter

from observatory.api._freshness import (
    DATA_TABLE,
    HEALTHY_MULT,
    INTERVALS_SEC,
    Freshness,
    cross_check_poller,
    freshness,
    worst,
)
from observatory.db.connection import get_conn
from observatory.pi.thermal import ThermalReadError, read_temp_c, read_throttled
from observatory.pi.thermal import derive_status as derive_pi_status

log = structlog.get_logger(__name__)
router = APIRouter()

LOCAL_SOURCES: tuple[str, ...] = ("weather", "muon")
EXTERNAL_SOURCES: tuple[str, ...] = ("usgs", "emsc", "bgs", "noaa", "blitzortung", "aurora")

# Whitelist of table names allowed in the f-string SQL below — guards against
# any future regression that lets a user-controlled value reach the query.
_ALLOWED_TABLES: frozenset[str] = frozenset(t for t, _ in DATA_TABLE.values())

# Sentinel age used when there is no event row yet. Any positive value
# >= STALE_MULT * max(INTERVALS_SEC) produces freshness="down" deterministically.
_NO_EVENT_AGE_SEC: int = 10**9


def _max_ts(conn: sqlite3.Connection, table: str, source_filter: str | None) -> int | None:
    if table not in _ALLOWED_TABLES:
        raise ValueError(f"table not in whitelist: {table!r}")
    if source_filter is not None:
        row = conn.execute(
            f"SELECT MAX(ts) AS m FROM {table} WHERE source=?",
            (source_filter,),
        ).fetchone()
    else:
        row = conn.execute(f"SELECT MAX(ts) AS m FROM {table}").fetchone()
    if not row:
        return None
    m = row["m"]
    return int(m) if m is not None else None


def _last_poll(conn: sqlite3.Connection, source: str) -> tuple[int | None, str | None]:
    row = conn.execute(
        "SELECT ended_at, status FROM poller_runs WHERE source=? ORDER BY ended_at DESC LIMIT 1",
        (source,),
    ).fetchone()
    if not row:
        return None, None
    return int(row["ended_at"]), str(row["status"])


def _pi_block() -> dict[str, Any]:
    """Return the pi.* block of the health response, tolerating vcgencmd failure."""
    try:
        temp = read_temp_c()
        throttled = read_throttled()
    except ThermalReadError as exc:
        log.warning("pi_thermal_unavailable", error=str(exc))
        return {
            "temp_c": None,
            "throttled": None,
            "status": "healthy",
            "warnings": ["pi_thermal_unavailable"],
        }
    status, warnings = derive_pi_status(temp, throttled)
    return {
        "temp_c": temp,
        "throttled": throttled,
        "status": status,
        "warnings": warnings,
    }


@router.get("/health")
def health() -> dict[str, Any]:
    """Compute the operational health snapshot."""
    now = int(time.time())
    out: dict[str, Any] = {"timestamp": now, "local": {}, "external": {}}
    worst_f: Freshness = "healthy"

    with get_conn() as conn:
        for name in LOCAL_SOURCES:
            table, src_filter = DATA_TABLE[name]
            interval = INTERVALS_SEC[name]
            last = _max_ts(conn, table, src_filter)
            age = (now - last) if last is not None else _NO_EVENT_AGE_SEC
            f = freshness(age, interval)
            out["local"][name] = {
                "last_event_ts": last,
                "freshness": f,
                "staleness_threshold_sec": HEALTHY_MULT * interval,
                "last_poll_status": None,
            }
            worst_f = worst(worst_f, f)

        for name in EXTERNAL_SOURCES:
            table, src_filter = DATA_TABLE[name]
            interval = INTERVALS_SEC[name]
            last = _max_ts(conn, table, src_filter)
            last_poll_ts, last_poll_status = _last_poll(conn, name)
            age = (now - last) if last is not None else _NO_EVENT_AGE_SEC
            event_f = freshness(age, interval)
            f = cross_check_poller(event_f, last_poll_status, last_poll_ts, now, interval)
            out["external"][name] = {
                "last_event_ts": last,
                "last_poll_ts": last_poll_ts,
                "last_poll_status": last_poll_status,
                "freshness": f,
                "staleness_threshold_sec": HEALTHY_MULT * interval,
            }
            worst_f = worst(worst_f, f)

    pi = _pi_block()
    out["pi"] = pi

    # Pi status escalation: critical -> overall down; warning -> at least stale.
    # A pi_thermal_unavailable (status="healthy") does NOT escalate — it is a
    # tooling issue, not a degraded service.
    if pi["status"] == "critical":
        worst_f = "down"
    elif pi["status"] == "warning" and worst_f == "healthy":
        worst_f = "stale"

    out["status"] = worst_f
    return out
