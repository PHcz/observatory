"""Phase 6 — shared aggregation helpers and Pydantic response models.

Implemented by Plan 06-01. Consumed by time-series routers in Plans 06-03..06.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

AggLiteral = Literal["raw", "minute", "hour", "day", "auto"]
AGG_VALUES: tuple[str, ...] = ("raw", "minute", "hour", "day", "auto")

# Bucket size in seconds for each aggregation level.
BUCKET_SECONDS: dict[str, int] = {
    "raw": 1,
    "minute": 60,
    "hour": 3600,
    "day": 86400,
}

# SQLite strftime templates per bucket (used by time-series routers in 06-03).
BUCKET_SQL_STRFTIME: dict[str, str] = {
    "minute": "strftime('%Y-%m-%d %H:%M', datetime(ts, 'unixepoch'))",
    "hour": "strftime('%Y-%m-%d %H:00', datetime(ts, 'unixepoch'))",
    "day": "strftime('%Y-%m-%d', datetime(ts, 'unixepoch'))",
}


class Window(BaseModel):
    """Echo of the actual time window used by a time-series query."""

    from_ts: int
    to_ts: int

    model_config = {"populate_by_name": True}


def resolve_agg(window_sec: int, requested: AggLiteral) -> str:
    """Map agg='auto' to a bucket based on window size; return requested unchanged otherwise.

    Thresholds (strictly less than):
        < 7200s  (2h)   -> raw
        < 172800s (2d)  -> minute
        < 5184000s (60d) -> hour
        else            -> day
    """
    if requested != "auto":
        return requested
    if window_sec < 7200:
        return "raw"
    if window_sec < 172800:
        return "minute"
    if window_sec < 5184000:
        return "hour"
    return "day"
