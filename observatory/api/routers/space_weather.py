"""Phase 6 — /api/space-weather time-series endpoint.

Implemented by Plan 06-03 (time-series) and Plan 06-04 (/api/space-weather/current).

Note on flare_class bucketing:
    flare_class is categorical ("C3.1", "M1.0", "X1.2") — AVG() is meaningless.
    We use MAX() which SQLite evaluates lexicographically. The class prefix ordering
    is A < B < C < M < X, so MAX() roughly picks the strongest flare in the bucket.
    This is an accepted approximation documented in 06-03-SUMMARY.md.
"""

from __future__ import annotations

import time

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
from observatory.db.connection import get_conn

router = APIRouter()


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

    with get_conn() as conn:
        if resolved == "raw":
            cursor = conn.execute(
                """
                SELECT ts, kp_index, solar_wind_kms, flare_class
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
                       MAX(flare_class) AS flare_class
                FROM space_weather
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
                        "kp_index": (
                            round(r["kp_index"], 2) if r["kp_index"] is not None else None
                        ),
                        "solar_wind_kms": (
                            round(r["solar_wind_kms"], 1)
                            if r["solar_wind_kms"] is not None
                            else None
                        ),
                        "flare_class": r["flare_class"],
                    }
                )

    return TimeSeriesResponse(
        window={"from": from_, "to": to},
        bucket_size_sec=BUCKET_SECONDS[resolved],
        agg=resolved,
        rows=rows,
    )


@router.get("/space-weather/current")
def get_space_weather_current() -> dict:  # type: ignore[type-arg]
    raise NotImplementedError("Plan 06-04 implements")
