"""Phase 6 — /api/current: all-sources snapshot endpoint.

Implemented by Plan 06-05.

Exposes:
  - ``build_current_snapshot(conn) -> dict`` — pure builder, importable by Plan
    06-06 for the WebSocket snapshot-on-connect frame.
  - ``GET /api/current`` — thin HTTP handler that opens a DB connection and
    delegates to the builder.

Source name mapping (snapshot key → INTERVALS_SEC key):
  - weather         → "weather"
  - muon            → "muon"
  - space_weather   → "noaa"
  - lightning_summary → "blitzortung"
  - aurora          → "aurora"

Freshness uses observatory.api._freshness helpers verbatim (no duplicate logic).
"""

from __future__ import annotations

import sqlite3
import time
from typing import Any

from fastapi import APIRouter

from observatory.api._freshness import (
    INTERVALS_SEC,
    cross_check_poller,
    freshness,
)
from observatory.api.astral_calc import get_astronomy
from observatory.config import settings
from observatory.db.connection import get_conn

router = APIRouter()

# Sentinel age that always resolves to freshness="down".
# Any value >= STALE_MULT * max(INTERVALS_SEC) works; 10^9 seconds (~31 years)
# is far beyond any real event horizon.
_NO_EVENT_AGE_SEC: int = 10**9


# ---------------------------------------------------------------------------
# Per-block data helpers
# ---------------------------------------------------------------------------


def _latest_weather(conn: sqlite3.Connection) -> dict[str, Any] | None:
    """Return the most recent weather row or None if table is empty."""
    row = conn.execute(
        "SELECT ts, temp_c, humidity_pct, pressure_hpa, lux FROM weather ORDER BY ts DESC LIMIT 1"
    ).fetchone()
    if row is None or row["ts"] is None:
        return None
    return {
        "ts": int(row["ts"]),
        "temp_c": round(float(row["temp_c"]), 2) if row["temp_c"] is not None else None,
        "humidity_pct": (
            round(float(row["humidity_pct"]), 1) if row["humidity_pct"] is not None else None
        ),
        "pressure_hpa": (
            round(float(row["pressure_hpa"]), 2) if row["pressure_hpa"] is not None else None
        ),
        "lux": round(float(row["lux"]), 1) if row["lux"] is not None else None,
    }


def _latest_muon(conn: sqlite3.Connection, now: int) -> dict[str, Any] | None:
    """Return muon summary dict or None if no rows exist at all."""
    latest_row = conn.execute(
        "SELECT MAX(ts) AS latest_event_ts, detector_pressure_hpa, detector_temp_c FROM muon_events"
    ).fetchone()
    if latest_row is None or latest_row["latest_event_ts"] is None:
        return None

    rate_row = conn.execute(
        "SELECT COUNT(*) AS cnt FROM muon_events WHERE ts > ?",
        (now - 60,),
    ).fetchone()
    rate_per_min: int = int(rate_row["cnt"]) if rate_row else 0

    return {
        "rate_per_min": rate_per_min,
        "latest_event_ts": int(latest_row["latest_event_ts"]),
        "detector_pressure_hpa": (
            round(float(latest_row["detector_pressure_hpa"]), 2)
            if latest_row["detector_pressure_hpa"] is not None
            else None
        ),
        "detector_temp_c": (
            round(float(latest_row["detector_temp_c"]), 2)
            if latest_row["detector_temp_c"] is not None
            else None
        ),
    }


def _latest_space_weather(conn: sqlite3.Connection) -> dict[str, Any] | None:
    """Return the most recent space_weather row or None if table is empty."""
    row = conn.execute(
        "SELECT ts, kp_index, solar_wind_kms, flare_class, flare_peak_ts"
        " FROM space_weather ORDER BY ts DESC LIMIT 1"
    ).fetchone()
    if row is None or row["ts"] is None:
        return None
    return {
        "ts": int(row["ts"]),
        "kp_index": (round(float(row["kp_index"]), 2) if row["kp_index"] is not None else None),
        "solar_wind_kms": (
            round(float(row["solar_wind_kms"]), 1) if row["solar_wind_kms"] is not None else None
        ),
        "flare_class": row["flare_class"],
        "flare_peak_ts": (int(row["flare_peak_ts"]) if row["flare_peak_ts"] is not None else None),
    }


def _lightning_aggregate(conn: sqlite3.Connection, now: int) -> dict[str, Any]:
    """Always returns an aggregate dict (never None); empty table yields all zeros."""
    today_start = now - (now % 86400)

    past_hour: int = conn.execute(
        "SELECT COUNT(*) FROM lightning_strikes WHERE ts > ?",
        (now - 3600,),
    ).fetchone()[0]

    past_24h: int = conn.execute(
        "SELECT COUNT(*) FROM lightning_strikes WHERE ts > ?",
        (now - 86400,),
    ).fetchone()[0]

    raw_nearest = conn.execute(
        "SELECT MIN(distance_km) FROM lightning_strikes WHERE ts > ?",
        (now - 86400,),
    ).fetchone()[0]

    total_today: int = conn.execute(
        "SELECT COUNT(*) FROM lightning_strikes WHERE ts >= ?",
        (today_start,),
    ).fetchone()[0]

    nearest_km: float | None = round(float(raw_nearest), 1) if raw_nearest is not None else None

    return {
        "past_hour": past_hour,
        "past_24h": past_24h,
        "nearest_km": nearest_km,
        "total_today": total_today,
        "ts": now,
    }


def _latest_aurora(conn: sqlite3.Connection) -> dict[str, Any] | None:
    """Return the most recent aurora_status row or None if table is empty."""
    row = conn.execute(
        "SELECT ts, status, detail FROM aurora_status ORDER BY ts DESC LIMIT 1"
    ).fetchone()
    if row is None or row["ts"] is None:
        return None
    return {
        "ts": int(row["ts"]),
        "status": row["status"],
        "detail": row["detail"],
    }


def _recent_earthquakes(conn: sqlite3.Connection, limit: int = 5) -> list[dict[str, Any]]:
    """Return up to `limit` most recent earthquakes across all sources."""
    rows = conn.execute(
        "SELECT ts, source, magnitude, place, depth_km FROM earthquakes ORDER BY ts DESC LIMIT ?",
        (limit,),
    ).fetchall()
    results = []
    for row in rows:
        results.append(
            {
                "ts": int(row["ts"]),
                "source": row["source"],
                "magnitude": (
                    round(float(row["magnitude"]), 1) if row["magnitude"] is not None else None
                ),
                "place": row["place"],
                "depth_km": (
                    round(float(row["depth_km"]), 1) if row["depth_km"] is not None else None
                ),
            }
        )
    return results


def _compute_block_freshness(
    conn: sqlite3.Connection,
    source_key: str,
    latest_ts: int | None,
    now: int,
) -> str:
    """Compute per-block freshness using _freshness helpers + poller_runs cross-check.

    For local sources (weather, muon) there are no poller_runs rows; the
    cross_check_poller call with None,None returns event freshness unchanged.

    Args:
        conn: Open DB connection.
        source_key: Key into INTERVALS_SEC (e.g. "noaa", "blitzortung").
        latest_ts: Most recent event timestamp or None if no rows.
        now: Current epoch seconds.

    Returns:
        "healthy" | "stale" | "down"
    """
    interval = INTERVALS_SEC[source_key]
    age: float = (now - latest_ts) if latest_ts is not None else _NO_EVENT_AGE_SEC
    event_f = freshness(age, interval)

    # Look up last poller_runs row for external sources.
    poll_row = conn.execute(
        "SELECT ended_at, status FROM poller_runs WHERE source=? ORDER BY ended_at DESC LIMIT 1",
        (source_key,),
    ).fetchone()
    last_poll_ts: int | None = None
    last_poll_status: str | None = None
    if poll_row is not None:
        last_poll_ts = int(poll_row["ended_at"]) if poll_row["ended_at"] is not None else None
        last_poll_status = str(poll_row["status"]) if poll_row["status"] is not None else None

    return cross_check_poller(event_f, last_poll_status, last_poll_ts, now, interval)


# ---------------------------------------------------------------------------
# Public builder — exported for Plan 06-06 WS snapshot
# ---------------------------------------------------------------------------


def build_current_snapshot(conn: sqlite3.Connection) -> dict[str, Any]:
    """Compose the all-sources current snapshot.

    Pure function: reads from `conn`, never writes. Re-entrant safe.
    Exported at module level so Plan 06-06 can call it for WS bootstrap frames.

    Args:
        conn: Open, read-only sqlite3.Connection (row_factory must support
              column-name access — observatory.db.connection.get_conn sets this).

    Returns:
        Dict with keys: timestamp, astronomy, weather, muon, space_weather,
        lightning_summary, aurora, earthquakes_recent.
    """
    now = int(time.time())

    # --- Data blocks ---
    weather_data = _latest_weather(conn)
    muon_data = _latest_muon(conn, now)
    sw_data = _latest_space_weather(conn)
    lightning_data = _lightning_aggregate(conn, now)
    aurora_data = _latest_aurora(conn)
    earthquakes = _recent_earthquakes(conn)

    # --- Per-block freshness ---
    # Snapshot key -> INTERVALS_SEC key mapping (per plan spec):
    #   weather         -> "weather"
    #   muon            -> "muon"
    #   space_weather   -> "noaa"
    #   lightning_summary -> "blitzortung"
    #   aurora          -> "aurora"
    weather_ts = weather_data["ts"] if weather_data is not None else None
    muon_ts = muon_data["latest_event_ts"] if muon_data is not None else None
    sw_ts = sw_data["ts"] if sw_data is not None else None
    # lightning freshness uses MAX(ts) from lightning_strikes
    lt_row = conn.execute("SELECT MAX(ts) AS m FROM lightning_strikes").fetchone()
    lt_ts: int | None = int(lt_row["m"]) if lt_row and lt_row["m"] is not None else None
    aurora_ts = aurora_data["ts"] if aurora_data is not None else None

    weather_freshness = _compute_block_freshness(conn, "weather", weather_ts, now)
    muon_freshness = _compute_block_freshness(conn, "muon", muon_ts, now)
    sw_freshness = _compute_block_freshness(conn, "noaa", sw_ts, now)
    lt_freshness = _compute_block_freshness(conn, "blitzortung", lt_ts, now)
    aurora_freshness = _compute_block_freshness(conn, "aurora", aurora_ts, now)

    # --- Astronomy ---
    astronomy = get_astronomy(settings.home_lat, settings.home_lon)

    return {
        "timestamp": now,
        "astronomy": astronomy,
        "weather": {
            "freshness": weather_freshness,
            "data": weather_data,
        },
        "muon": {
            "freshness": muon_freshness,
            "data": muon_data,
        },
        "space_weather": {
            "freshness": sw_freshness,
            "data": sw_data,
        },
        "lightning_summary": {
            "freshness": lt_freshness,
            "data": lightning_data,
        },
        "aurora": {
            "freshness": aurora_freshness,
            "data": aurora_data,
        },
        "earthquakes_recent": earthquakes,
    }


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------


@router.get("/current")
def get_current() -> dict[str, Any]:
    """Return the all-sources current state snapshot.

    This is the primary endpoint for dashboard initial paint and the WS
    bootstrap frame. All 8 top-level keys are always present; per-source
    data blocks are None when the respective table is empty (with freshness
    set to "down").

    earthquakes_recent always returns a list (empty when no rows).
    lightning_summary.data is always a dict (zeros for empty table).
    """
    with get_conn() as conn:
        return build_current_snapshot(conn)
