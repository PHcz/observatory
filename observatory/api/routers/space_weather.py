"""Phase 6 — /api/space-weather time-series endpoint.

Implemented by Plan 06-03 (time-series) and Plan 06-04 (/api/space-weather/current).

Note on flare_class bucketing:
    flare_class is categorical ("C3.1", "M1.0", "X1.2") — AVG() is meaningless.
    We use MAX() which SQLite evaluates lexicographically. The class prefix ordering
    is A < B < C < M < X, so MAX() roughly picks the strongest flare in the bucket.
    This is an accepted approximation documented in 06-03-SUMMARY.md.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from observatory.api._serializers import (
    BUCKET_SECONDS,
    BUCKET_SQL_STRFTIME,
    DEFAULT_WINDOW_SEC,
    MAX_ROWS,
    SPARSE_LIMITS,
    AggLiteral,
    TimeSeriesResponse,
    enforce_window_limits,
    resolve_agg,
)
from observatory.db.connection import get_conn

router = APIRouter()

# Column -> decimals for the public payload (None = pass through unrounded).
# Shared by /api/space-weather/current and the /api/current snapshot so the two
# cannot drift apart.
_PUBLIC_FIELDS: dict[str, int | None] = {
    "kp_index": 2,
    "solar_wind_kms": 1,
    "flare_class": None,
    "flare_peak_ts": None,
    "solar_wind_density": 1,
    "imf_bz_nt": 1,
    "imf_bt_nt": 1,
    "proton_flux_10mev": 3,
    "noaa_scale_r": None,
    "noaa_scale_s": None,
    "noaa_scale_g": None,
}
_SELECT_COLUMNS = ", ".join(["ts", *_PUBLIC_FIELDS])


def _rounded(value: object, decimals: int | None) -> object:
    if value is None or decimals is None:
        return value
    return round(float(value), decimals)  # type: ignore[arg-type]


def serialize_space_weather(row: Mapping[str, Any]) -> dict[str, object]:
    """Public JSON shape of one space_weather row."""
    out: dict[str, object] = {"ts": int(row["ts"])}
    for col, decimals in _PUBLIC_FIELDS.items():
        out[col] = _rounded(row[col], decimals)
    return out


def latest_space_weather(conn: sqlite3.Connection) -> dict[str, object] | None:
    row = conn.execute(
        f"SELECT {_SELECT_COLUMNS} FROM space_weather ORDER BY ts DESC LIMIT 1"  # nosec B608
    ).fetchone()
    if row is None or row["ts"] is None:
        return None
    return serialize_space_weather(row)


@router.get("/space-weather", response_model=TimeSeriesResponse)
def get_space_weather(
    from_: int | None = Query(default=None, alias="from", ge=0),
    to: int | None = Query(default=None, ge=0),
    agg: AggLiteral = Query(default="auto"),  # noqa: B008
) -> TimeSeriesResponse:
    """Return space-weather time-series for the requested window.

    Query params:
        from: epoch-seconds start (default: now - 86400)
        to:   epoch-seconds end   (default: now)
        agg:  raw | minute | hour | day | auto (default: auto)

    Response shape:
        {"window": {"from": int, "to": int}, "bucket_size_sec": int, "agg": str, "rows": [...]}

    flare_class: for raw agg, returned as-is from DB. For bucketed agg,
        MAX(flare_class) is used — lexicographic max approximates strongest class
        (X > M > C > B > A alphabetically, which matches physical ordering).
    """
    now = int(time.time())
    to = to if to is not None else now
    from_ = from_ if from_ is not None else (to - DEFAULT_WINDOW_SEC)

    if from_ >= to:
        raise HTTPException(status_code=422, detail="from must be < to")

    window_sec = to - from_
    resolved = resolve_agg(window_sec, agg)
    enforce_window_limits(window_sec, resolved, SPARSE_LIMITS)

    with get_conn() as conn:
        if resolved == "raw":
            cursor = conn.execute(
                """
                SELECT ts, kp_index, solar_wind_kms, flare_class,
                       solar_wind_density, imf_bz_nt, imf_bt_nt, proton_flux_10mev,
                       noaa_scale_r, noaa_scale_s, noaa_scale_g
                FROM space_weather
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
                       AVG(kp_index) AS kp_index,
                       AVG(solar_wind_kms) AS solar_wind_kms,
                       MAX(flare_class) AS flare_class,
                       AVG(solar_wind_density) AS solar_wind_density,
                       AVG(imf_bz_nt) AS imf_bz_nt,
                       AVG(imf_bt_nt) AS imf_bt_nt,
                       MAX(proton_flux_10mev) AS proton_flux_10mev,
                       MAX(noaa_scale_r) AS noaa_scale_r,
                       MAX(noaa_scale_s) AS noaa_scale_s,
                       MAX(noaa_scale_g) AS noaa_scale_g
                FROM space_weather
                WHERE ts BETWEEN ? AND ?
                GROUP BY {bucket_expr}
                ORDER BY ts ASC
                LIMIT ?
                """,  # nosec B608
                (from_, to, MAX_ROWS),
            )
            rows = [
                {
                    k: v
                    for k, v in serialize_space_weather({**dict(r), "flare_peak_ts": None}).items()
                    if k != "flare_peak_ts"
                }
                for r in cursor
            ]

    return TimeSeriesResponse(
        window={"from": from_, "to": to},
        bucket_size_sec=BUCKET_SECONDS[resolved],
        agg=resolved,
        rows=rows,
    )


@router.get("/space-weather/current")
def get_space_weather_current() -> dict[str, object]:
    """Return the latest space_weather row.

    Response shape::

        {
            "ts": int,
            "kp_index": float | None,      # rounded to 2dp
            "solar_wind_kms": float | None, # rounded to 1dp
            "flare_class": str | None,
            "flare_peak_ts": int | None,
            "solar_wind_density": float | None,  # p/cm^3, 1dp
            "imf_bz_nt": float | None,           # GSM Bz, 1dp (negative = southward)
            "imf_bt_nt": float | None,           # 1dp
            "proton_flux_10mev": float | None,   # GOES >=10 MeV pfu, 3dp
            "noaa_scale_r" / "_s" / "_g": int | None   # current NOAA scale levels 0-5
        }

    Raises 404 if no space_weather rows exist.
    """
    with get_conn() as conn:
        latest = latest_space_weather(conn)
    if latest is None:
        raise HTTPException(status_code=404, detail="No space_weather rows yet")
    return latest
