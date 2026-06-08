"""Phase 6 — /api/weather time-series endpoint.

Implemented by Plan 06-03. Provides bucketed weather readings from the local
SQLite store with agg=auto|raw|minute|hour|day query support.

Extended in Plan 16-03 with:
  GET /api/weather/today   — today-so-far stats since local midnight
  GET /api/weather/outlook — Zambretti forecast from MSLP + 3h tendency
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from observatory.api._serializers import (
    BUCKET_SECONDS,
    BUCKET_SQL_STRFTIME,
    DEFAULT_WINDOW_SEC,
    MAX_ROWS,
    AggLiteral,
    TimeSeriesResponse,
    resolve_agg,
)
from observatory.config import settings
from observatory.db.connection import get_conn
from observatory.weather.derived import (
    ZAMBRETTI_FORECAST,
    classify_tendency,
    local_midnight_ts,
    station_to_mslp,
    today_so_far,
    zambretti_z,
)

router = APIRouter()


@router.get("/weather", response_model=TimeSeriesResponse)
def get_weather(
    from_: int | None = Query(default=None, alias="from", ge=0),
    to: int | None = Query(default=None, ge=0),
    agg: AggLiteral = Query(default="auto"),  # noqa: B008
) -> TimeSeriesResponse:
    """Return weather time-series for the requested window.

    Query params:
        from: epoch-seconds start (default: now - 86400)
        to:   epoch-seconds end   (default: now)
        agg:  raw | minute | hour | day | auto (default: auto)

    Response shape:
        {"window": {"from": int, "to": int}, "bucket_size_sec": int, "agg": str, "rows": [...]}
    """
    now = int(time.time())
    to = to if to is not None else now
    from_ = from_ if from_ is not None else (to - DEFAULT_WINDOW_SEC)

    if from_ >= to:
        raise HTTPException(status_code=422, detail="from must be < to")

    window_sec = to - from_
    resolved = resolve_agg(window_sec, agg)

    with get_conn() as conn:
        if resolved == "raw":
            cursor = conn.execute(
                """
                SELECT ts, node_id, temp_c, humidity_pct, pressure_hpa, lux
                FROM weather
                WHERE ts BETWEEN ? AND ?
                ORDER BY ts ASC
                LIMIT ?
                """,
                (from_, to, MAX_ROWS),
            )
            rows = [dict(r) for r in cursor]
        else:
            # Bucket template comes from whitelist — no user input interpolated.
            # nosec B608
            bucket_expr = BUCKET_SQL_STRFTIME[resolved]
            cursor = conn.execute(
                f"""
                SELECT MIN(ts) AS ts,
                       AVG(temp_c) AS temp_c,
                       AVG(humidity_pct) AS humidity_pct,
                       AVG(pressure_hpa) AS pressure_hpa,
                       AVG(lux) AS lux
                FROM weather
                WHERE ts BETWEEN ? AND ?
                GROUP BY {bucket_expr}
                ORDER BY ts ASC
                LIMIT ?
                """,  # nosec B608
                (from_, to, MAX_ROWS),
            )
            raw_rows = [dict(r) for r in cursor]
            rows = []
            for r in raw_rows:
                rows.append(
                    {
                        "ts": r["ts"],
                        "temp_c": round(r["temp_c"], 2) if r["temp_c"] is not None else None,
                        "humidity_pct": (
                            round(r["humidity_pct"], 1) if r["humidity_pct"] is not None else None
                        ),
                        "pressure_hpa": (
                            round(r["pressure_hpa"], 2) if r["pressure_hpa"] is not None else None
                        ),
                        "lux": round(r["lux"], 1) if r["lux"] is not None else None,
                    }
                )

    return TimeSeriesResponse(
        window={"from": from_, "to": to},
        bucket_size_sec=BUCKET_SECONDS[resolved],
        agg=resolved,
        rows=rows,
    )


@router.get("/weather/today")
def get_weather_today() -> dict[str, Any]:
    """Return today-so-far stats since local midnight.

    Queries weather since the local midnight boundary (timezone-aware).
    Returns high/low temp, pressure range, peak lux, and derived dewpoint range.
    Empty DB or no rows since midnight returns 200 with all-null values.

    Response keys:
        high_c, low_c, pressure_high_hpa, pressure_low_hpa,
        peak_lux, dewpoint_high_c, dewpoint_low_c, since_ts
    """
    midnight = local_midnight_ts(settings.home_timezone)

    with get_conn() as conn:
        # Use the most-recent node_id if available; fall back to empty-state.
        row = conn.execute("SELECT node_id FROM weather ORDER BY ts DESC LIMIT 1").fetchone()
        if row is None:
            return {
                "high_c": None,
                "low_c": None,
                "pressure_high_hpa": None,
                "pressure_low_hpa": None,
                "peak_lux": None,
                "dewpoint_high_c": None,
                "dewpoint_low_c": None,
                "since_ts": None,
            }
        node_id = row["node_id"]
        return today_so_far(conn, midnight, node_id)


@router.get("/weather/outlook")
def get_weather_outlook() -> dict[str, Any]:
    """Return a Zambretti forecast computed from MSLP + 3h pressure tendency.

    MSLP is computed using station_to_mslp(settings.station_altitude_m).
    Tendency is derived from the pressure delta over the last 3 hours.

    MSLP CONTRACT (per plan 16-03):
        - mslp_hpa is ALWAYS returned whenever a latest reading exists.
        - mslp_adjusted is FALSE when station_altitude_m == 0.0 (sea-level /
          unset); the value is still returned (sea-level install sees its MSLP
          which simply equals station pressure).
        - mslp_adjusted is TRUE when station_altitude_m > 0 (real correction).
        - When there is insufficient pressure history (<3h of data), verdict and
          direction are null but mslp_hpa / mslp_adjusted are still returned if
          a latest reading exists.

    Response keys:
        verdict, direction, based_on_hpa_per_3h, z_score, mslp_hpa, mslp_adjusted
    """
    now = int(time.time())
    three_hours_ago = now - 3 * 3600

    with get_conn() as conn:
        # Latest reading for current pressure + temp (needed for MSLP).
        latest_row = conn.execute(
            """
            SELECT pressure_hpa, temp_c
            FROM weather
            WHERE pressure_hpa IS NOT NULL
            ORDER BY ts DESC
            LIMIT 1
            """
        ).fetchone()

        if latest_row is None:
            # No data at all — full empty state.
            return {
                "verdict": None,
                "direction": None,
                "based_on_hpa_per_3h": None,
                "z_score": None,
                "mslp_hpa": None,
                "mslp_adjusted": False,
            }

        latest_pressure = latest_row["pressure_hpa"]
        latest_temp = latest_row["temp_c"] or 15.0  # fallback when temp is null

        # Compute MSLP — always done when we have a pressure reading.
        mslp = station_to_mslp(
            latest_pressure,
            settings.station_altitude_m,
            latest_temp,
        )
        mslp_adjusted = settings.station_altitude_m > 0.0

        # Pressure ~3h ago for tendency.
        old_row = conn.execute(
            """
            SELECT pressure_hpa
            FROM weather
            WHERE ts <= ? AND pressure_hpa IS NOT NULL
            ORDER BY ts DESC
            LIMIT 1
            """,
            (three_hours_ago,),
        ).fetchone()

        if old_row is None:
            # Insufficient history for tendency — return empty forecast
            # but still include MSLP fields.
            return {
                "verdict": None,
                "direction": None,
                "based_on_hpa_per_3h": None,
                "z_score": None,
                "mslp_hpa": round(mslp, 1),
                "mslp_adjusted": mslp_adjusted,
            }

        delta = latest_pressure - old_row["pressure_hpa"]
        tendency = classify_tendency(delta)
        z = zambretti_z(mslp, tendency)
        verdict = ZAMBRETTI_FORECAST[z]

        return {
            "verdict": verdict,
            "direction": tendency,
            "based_on_hpa_per_3h": round(delta, 2),
            "z_score": z,
            "mslp_hpa": round(mslp, 1),
            "mslp_adjusted": mslp_adjusted,
        }
