"""Phase 6 — /api/lightning/summary aggregate endpoint.

Implemented by Plan 06-04.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter

from observatory.db.connection import get_conn

router = APIRouter()


@router.get("/lightning/summary")
def get_lightning_summary() -> dict[str, Any]:
    """Return aggregate lightning strike counts and nearest strike distance.

    No query params — always returns current-moment aggregates.

    Response shape::

        {
            "past_hour":   int,           # strikes in last 3600s
            "past_24h":    int,           # strikes in last 86400s
            "nearest_km":  float | None,  # MIN(distance_km) in last 86400s, 1dp
            "total_today": int,           # strikes since start of UTC day
            "ts":          int            # epoch-seconds at query time
        }
    """
    now = int(time.time())
    today_start = now - (now % 86400)

    with get_conn() as conn:
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

    nearest_km: float | None = round(raw_nearest, 1) if raw_nearest is not None else None

    return {
        "past_hour": past_hour,
        "past_24h": past_24h,
        "nearest_km": nearest_km,
        "total_today": total_today,
        "ts": now,
    }
