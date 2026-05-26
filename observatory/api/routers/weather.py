"""Phase 6 — /api/weather time-series endpoint.

Implemented by Plan 06-03. Provides bucketed weather readings from the local
SQLite store with agg=auto|raw|minute|hour|day query support.
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
