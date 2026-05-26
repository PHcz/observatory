"""Phase 6 — /api/earthquakes paginated list endpoint.

Implemented by Plan 06-04.

Pagination uses cursor-based approach via `before_ts` parameter.
`next_before_ts` in the response is the ts of the oldest row in the page
when the page is full (len == limit), else None.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Query

from observatory.api._pagination import DEFAULT_LIMIT, MAX_LIMIT, resolve_before_ts
from observatory.db.connection import get_conn

router = APIRouter()


@router.get("/earthquakes")
def get_earthquakes(
    from_: int | None = Query(default=None, alias="from", ge=0),
    to: int | None = Query(default=None, ge=0),
    min_mag: float = Query(default=0.0, ge=0.0, le=10.0),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    before_ts: int | None = Query(default=None, ge=0),
) -> dict[str, Any]:
    """Return a paginated list of earthquakes ordered by ts DESC.

    Query params:
        from:      epoch-seconds start (default: to - 86400)
        to:        epoch-seconds end   (default: now)
        min_mag:   minimum magnitude filter (default: 0.0)
        limit:     max rows per page (1..MAX_LIMIT, default: DEFAULT_LIMIT)
        before_ts: cursor — only return rows with ts strictly < this value

    Response shape::

        {
            "window": {"from": int, "to": int},
            "limit": int,
            "rows": [
                {
                    "ts": int,
                    "source": str,
                    "external_id": str,
                    "magnitude": float | None,
                    "depth_km": float | None,
                    "latitude": float | None,
                    "longitude": float | None,
                    "place": str | None
                },
                ...
            ],
            "next_before_ts": int | None
        }

    ``next_before_ts`` is set to the oldest ts in the page when ``len(rows) == limit``
    (indicating more rows may exist), else ``None``.
    """
    now = int(time.time())
    to = to if to is not None else now
    from_ = from_ if from_ is not None else (to - 86400)

    # Cursor: rows strictly older than this ts. Default: include everything up to `to`.
    effective_before_ts = resolve_before_ts(before_ts, to + 1)

    with get_conn() as conn:
        cursor = conn.execute(
            """
            SELECT ts, source, external_id, magnitude, depth_km, latitude, longitude, place
            FROM earthquakes
            WHERE ts BETWEEN ? AND ?
              AND magnitude >= ?
              AND ts < ?
            ORDER BY ts DESC
            LIMIT ?
            """,
            (from_, to, min_mag, effective_before_ts, limit),
        )
        rows: list[dict[str, Any]] = [dict(r) for r in cursor]

    next_before_ts: int | None = rows[-1]["ts"] if len(rows) == limit else None

    return {
        "window": {"from": from_, "to": to},
        "limit": limit,
        "rows": rows,
        "next_before_ts": next_before_ts,
    }
