"""Phase 6 — shared aggregation helpers and Pydantic response models.

Implemented by Plan 06-01. Consumed by time-series routers in Plans 06-03..06.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel

DEFAULT_WINDOW_SEC: int = 86400  # 24h
MAX_ROWS: int = 5000  # hard cap defensive

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


class TimeSeriesResponse(BaseModel):
    """Shared response shape for all time-series REST endpoints.

    Serializes as::

        {
            "window": {"from": int, "to": int},
            "bucket_size_sec": int,
            "agg": str,
            "rows": [...]
        }
    """

    window: dict[str, int]
    bucket_size_sec: int
    agg: str
    rows: list[dict[str, Any]]


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


@dataclass(frozen=True)
class WindowLimits:
    """Largest time window a series endpoint will scan (security audit M3).

    The cost is rows SCANNED, not rows returned, so limits are per table: the
    muon table is dense (~150 events/min), and agg=day over 30 days scanned ~6.5 M
    rows -- 60 s of Pi CPU. Weather and space weather are sparse.
    """

    max_window_sec: int
    max_raw_sec: int


# Dense: the dashboard asks for 24 h; 2 days keeps a request to a few seconds.
MUON_LIMITS = WindowLimits(max_window_sec=2 * 86_400, max_raw_sec=2 * 3_600)
# Sparse (~288 rows/day): a year is cheap.
SPARSE_LIMITS = WindowLimits(max_window_sec=366 * 86_400, max_raw_sec=31 * 86_400)


def enforce_window_limits(window_sec: int, resolved_agg: str, limits: WindowLimits) -> None:
    """Raise 422 if a query would scan more than this series allows."""
    if window_sec > limits.max_window_sec:
        raise HTTPException(
            status_code=422,
            detail=(
                f"window of {window_sec}s exceeds the {limits.max_window_sec}s maximum "
                "for this series"
            ),
        )
    if resolved_agg == "raw" and window_sec > limits.max_raw_sec:
        raise HTTPException(
            status_code=422,
            detail=(
                f"raw rows are limited to a {limits.max_raw_sec}s window; "
                "use agg=minute, hour or day"
            ),
        )
