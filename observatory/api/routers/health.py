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
    POLL_ANCHORED_SOURCES,
    Freshness,
    cadence_warning,
    cross_check_poller,
    freshness,
    worst,
)
from observatory.config import settings
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
    # SQL identifiers (table names) cannot be parameter-bound in sqlite3; we
    # interpolate via f-string after validating `table` against a fixed
    # _ALLOWED_TABLES allowlist (no user input reaches this string). Values
    # (source_filter) ARE parameter-bound. Bandit B608 false positive.
    if source_filter is not None:
        row = conn.execute(
            f"SELECT MAX(ts) AS m FROM {table} WHERE source=?",  # nosec B608
            (source_filter,),
        ).fetchone()
    else:
        row = conn.execute(f"SELECT MAX(ts) AS m FROM {table}").fetchone()  # nosec B608
    if not row:
        return None
    m = row["m"]
    return int(m) if m is not None else None


def _forecast_last_fetched(conn: sqlite3.Connection) -> int | None:
    """Return forecast_meta.fetched_at (when the forecast was last polled).

    This is the freshness anchor for the `forecast` source — NOT MAX(ts) of
    forecast_hourly/daily, whose ts runs ~7 days into the future and would
    therefore always look fresh (10-RESEARCH Open Question 2).
    """
    row = conn.execute("SELECT fetched_at FROM forecast_meta WHERE id = 1").fetchone()
    if not row:
        return None
    val = row["fetched_at"]
    return int(val) if val is not None else None


def _air_quality_last_fetched(conn: sqlite3.Connection) -> int | None:
    """Return air_quality_meta.fetched_at (when the snapshot was last polled).

    This is the freshness anchor for the `air_quality` source — NOT MAX(ts) of
    the single-row air_quality snapshot (mirrors the forecast carve-out).
    """
    row = conn.execute("SELECT fetched_at FROM air_quality_meta WHERE id = 1").fetchone()
    if not row:
        return None
    val = row["fetched_at"]
    return int(val) if val is not None else None


def _nmdb_last_fetched(conn: sqlite3.Connection) -> int | None:
    """Return nmdb_meta.fetched_at (when the NMDB counts were last polled).

    This is the freshness anchor for the `nmdb` source — NOT MAX(ts) of
    nmdb_counts (the count series carries upstream data time, which can lag or
    look fresh independently of our poll; Pitfall 2). Mirrors the
    forecast/air_quality carve-out.
    """
    row = conn.execute("SELECT fetched_at FROM nmdb_meta WHERE id = 1").fetchone()
    if not row:
        return None
    val = row["fetched_at"]
    return int(val) if val is not None else None


def _last_poll(conn: sqlite3.Connection, source: str) -> tuple[int | None, str | None]:
    row = conn.execute(
        "SELECT ended_at, status FROM poller_runs WHERE source=? ORDER BY ended_at DESC LIMIT 1",
        (source,),
    ).fetchone()
    if not row:
        return None, None
    return int(row["ended_at"]), str(row["status"])


def _last_successful_poll(conn: sqlite3.Connection, source: str) -> int | None:
    """Return ended_at of the most recent SUCCESSFUL (or partial) poll for source.

    Freshness anchor for POLL_ANCHORED_SOURCES — proof the feed is alive,
    independent of whether a (sporadic) event happened to arrive. ``partial``
    counts as alive (e.g. NOAA-style 1-of-N) consistent with cross_check_poller.
    """
    row = conn.execute(
        "SELECT ended_at FROM poller_runs "
        "WHERE source=? AND status IN ('success', 'partial') "
        "ORDER BY ended_at DESC LIMIT 1",
        (source,),
    ).fetchone()
    if not row or row["ended_at"] is None:
        return None
    return int(row["ended_at"])


def _pi_block() -> dict[str, Any]:
    """Return the pi.* block of the health response, tolerating vcgencmd failure."""
    try:
        temp = read_temp_c()
        throttled = read_throttled()
    except (ThermalReadError, FileNotFoundError, OSError) as exc:
        # ThermalReadError: vcgencmd ran but returned non-zero / unparseable output
        # FileNotFoundError: vcgencmd binary missing (e.g. dev Mac, broken install)
        # OSError: catch-all for other subprocess-spawn failures
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
            entry: dict[str, Any] = {
                "last_event_ts": last,
                "freshness": f,
                "staleness_threshold_sec": HEALTHY_MULT * interval,
                "last_poll_status": None,
                "cadence_warning": cadence_warning(now, last, name),
            }
            if name == "weather":
                # CONTEXT.md §specifics: surface configured nickname so future
                # multi-node deploys propagate via env var, not code edits.
                entry["source"] = settings.weather_nickname
            out["local"][name] = entry
            worst_f = worst(worst_f, f)

        for name in EXTERNAL_SOURCES:
            table, src_filter = DATA_TABLE[name]
            interval = INTERVALS_SEC[name]
            last = _max_ts(conn, table, src_filter)
            last_poll_ts, last_poll_status = _last_poll(conn, name)
            if name in POLL_ANCHORED_SOURCES:
                # Sporadic upstream (quakes/lightning/aurora): anchor the dot on
                # the last SUCCESSFUL poll, NOT MAX(ts) of events — a quiet spell
                # is not a fault. last_event_ts is still reported (informational).
                ok_poll = _last_successful_poll(conn, name)
                anchor_age = (now - ok_poll) if ok_poll is not None else _NO_EVENT_AGE_SEC
                base_f = freshness(anchor_age, interval)
            else:
                # Continuous source (noaa writes a row per poll): event age is right.
                age = (now - last) if last is not None else _NO_EVENT_AGE_SEC
                base_f = freshness(age, interval)
            f = cross_check_poller(base_f, last_poll_status, last_poll_ts, now, interval)
            out["external"][name] = {
                "last_event_ts": last,
                "last_poll_ts": last_poll_ts,
                "last_poll_status": last_poll_status,
                "freshness": f,
                "staleness_threshold_sec": HEALTHY_MULT * interval,
                "cadence_warning": cadence_warning(now, last, name),
            }
            worst_f = worst(worst_f, f)

        # forecast: bespoke external entry. Freshness anchors on
        # forecast_meta.fetched_at (NOT MAX(ts) — the horizon is ~7 days out and
        # would always look fresh). Kept off the EXTERNAL_SOURCES loop because
        # that path routes through _max_ts(ts), which is the wrong column here.
        fc_interval = INTERVALS_SEC["forecast"]
        fc_last = _forecast_last_fetched(conn)
        fc_poll_ts, fc_poll_status = _last_poll(conn, "forecast")
        # Freshness anchor: forecast_meta.fetched_at. If a meta row hasn't been
        # written yet but the last poll succeeded, the successful poll timestamp
        # is itself proof of a fresh fetch (the writer upserts meta on success).
        fc_anchor = fc_last
        if fc_anchor is None and fc_poll_status in ("success", "partial"):
            fc_anchor = fc_poll_ts
        fc_age = (now - fc_anchor) if fc_anchor is not None else _NO_EVENT_AGE_SEC
        fc_event_f = freshness(fc_age, fc_interval)
        fc_f = cross_check_poller(fc_event_f, fc_poll_status, fc_poll_ts, now, fc_interval)
        out["external"]["forecast"] = {
            "last_event_ts": fc_last,
            "last_poll_ts": fc_poll_ts,
            "last_poll_status": fc_poll_status,
            "freshness": fc_f,
            "staleness_threshold_sec": HEALTHY_MULT * fc_interval,
            "cadence_warning": cadence_warning(now, fc_last, "forecast"),
        }
        worst_f = worst(worst_f, fc_f)

        # air_quality: bespoke external entry. Freshness anchors on
        # air_quality_meta.fetched_at (NOT MAX(ts) of the single-row snapshot).
        # Kept off the EXTERNAL_SOURCES loop because that path routes through
        # _max_ts(ts), which is the wrong column here — mirrors forecast above.
        aq_interval = INTERVALS_SEC["air_quality"]
        aq_last = _air_quality_last_fetched(conn)
        aq_poll_ts, aq_poll_status = _last_poll(conn, "air_quality")
        aq_anchor = aq_last
        if aq_anchor is None and aq_poll_status in ("success", "partial"):
            aq_anchor = aq_poll_ts
        aq_age = (now - aq_anchor) if aq_anchor is not None else _NO_EVENT_AGE_SEC
        aq_event_f = freshness(aq_age, aq_interval)
        aq_f = cross_check_poller(aq_event_f, aq_poll_status, aq_poll_ts, now, aq_interval)
        out["external"]["air_quality"] = {
            "last_event_ts": aq_last,
            "last_poll_ts": aq_poll_ts,
            "last_poll_status": aq_poll_status,
            "freshness": aq_f,
            "staleness_threshold_sec": HEALTHY_MULT * aq_interval,
            "cadence_warning": cadence_warning(now, aq_last, "air_quality"),
        }
        worst_f = worst(worst_f, aq_f)

        # nmdb: bespoke external entry. Freshness anchors on nmdb_meta.fetched_at
        # (NOT MAX(ts) of the count series — Pitfall 2). Kept off the
        # EXTERNAL_SOURCES loop because that path routes through _max_ts(ts), which
        # is the wrong column here — mirrors forecast/air_quality above.
        nmdb_interval = INTERVALS_SEC["nmdb"]
        nmdb_last = _nmdb_last_fetched(conn)
        nmdb_poll_ts, nmdb_poll_status = _last_poll(conn, "nmdb")
        nmdb_anchor = nmdb_last
        if nmdb_anchor is None and nmdb_poll_status in ("success", "partial"):
            nmdb_anchor = nmdb_poll_ts
        nmdb_age = (now - nmdb_anchor) if nmdb_anchor is not None else _NO_EVENT_AGE_SEC
        nmdb_event_f = freshness(nmdb_age, nmdb_interval)
        nmdb_f = cross_check_poller(
            nmdb_event_f, nmdb_poll_status, nmdb_poll_ts, now, nmdb_interval
        )
        out["external"]["nmdb"] = {
            "last_event_ts": nmdb_last,
            "last_poll_ts": nmdb_poll_ts,
            "last_poll_status": nmdb_poll_status,
            "freshness": nmdb_f,
            "staleness_threshold_sec": HEALTHY_MULT * nmdb_interval,
            "cadence_warning": cadence_warning(now, nmdb_last, "nmdb"),
        }
        worst_f = worst(worst_f, nmdb_f)

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
