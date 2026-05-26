"""Phase 6 — /api/muon time-series endpoint.

Implemented by Plan 06-03. Provides bucketed muon event counts from the local
SQLite store with agg=auto|raw|minute|hour|day query support.

rate_per_min derivation:
    For bucketed aggregations, COUNT(*) events per bucket is stored as event_count.
    rate_per_min = event_count * 60 / BUCKET_SECONDS[resolved], rounded to 2 dp.
    This field is ABSENT for raw agg rows — do not include a null; omit it entirely
    (documented in 06-03-SUMMARY.md for Phase 7 frontend handling).
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


@router.get("/muon", response_model=TimeSeriesResponse)
def get_muon(
    from_: int | None = Query(default=None, alias="from", ge=0),
    to: int | None = Query(default=None, ge=0),
    agg: AggLiteral = Query(default="auto"),  # noqa: B008
) -> TimeSeriesResponse:
    """Return muon event time-series for the requested window.

    Query params:
        from: epoch-seconds start (default: now - 86400)
        to:   epoch-seconds end   (default: now)
        agg:  raw | minute | hour | day | auto (default: auto)

    Response shape:
        {"window": {"from": int, "to": int}, "bucket_size_sec": int, "agg": str, "rows": [...]}

    Raw rows: ts, detector_pressure_hpa, detector_temp_c, amplitude, coincidence (integer).
    Bucketed rows: ts, event_count, rate_per_min, detector_pressure_hpa, detector_temp_c, amplitude.
    Note: rate_per_min is ABSENT (not null) in raw rows.
    """
    now = int(time.time())
    to = to if to is not None else now
    from_ = from_ if from_ is not None else (to - DEFAULT_WINDOW_SEC)

    if from_ >= to:
        raise HTTPException(status_code=422, detail="from must be < to")

    window_sec = to - from_
    resolved = resolve_agg(window_sec, agg)
    bucket_sec = BUCKET_SECONDS[resolved]

    with get_conn() as conn:
        if resolved == "raw":
            cursor = conn.execute(
                """
                SELECT ts, detector_pressure_hpa, detector_temp_c, amplitude, coincidence
                FROM muon_events
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
                       COUNT(*) AS event_count,
                       AVG(detector_pressure_hpa) AS detector_pressure_hpa,
                       AVG(detector_temp_c) AS detector_temp_c,
                       AVG(amplitude) AS amplitude
                FROM muon_events
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
                event_count: int = r["event_count"]
                rate_per_min = round(event_count * 60 / bucket_sec, 2)
                rows.append(
                    {
                        "ts": r["ts"],
                        "event_count": event_count,
                        "rate_per_min": rate_per_min,
                        "detector_pressure_hpa": (
                            round(r["detector_pressure_hpa"], 2)
                            if r["detector_pressure_hpa"] is not None
                            else None
                        ),
                        "detector_temp_c": (
                            round(r["detector_temp_c"], 2)
                            if r["detector_temp_c"] is not None
                            else None
                        ),
                        "amplitude": (
                            round(r["amplitude"], 4) if r["amplitude"] is not None else None
                        ),
                    }
                )

    return TimeSeriesResponse(
        window={"from": from_, "to": to},
        bucket_size_sec=bucket_sec,
        agg=resolved,
        rows=rows,
    )
