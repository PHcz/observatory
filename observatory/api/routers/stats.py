"""Phase 6 — /api/stats/today daily aggregate endpoint.

Implemented by Plan 06-04.

Stats cover the current UTC day (since midnight UTC).
max_muon_rate_per_min uses a SQL bucket-by-minute approach:
    SELECT MAX(rate) FROM (
        SELECT COUNT(*) AS rate
        FROM muon_events WHERE ts >= :today_start
        GROUP BY strftime('%Y-%m-%d %H:%M', datetime(ts, 'unixepoch'))
    )
Returns 0 when no muon events exist today (COALESCE).
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter

from observatory.db.connection import get_conn

router = APIRouter()

_MUON_RATE_SQL = """
SELECT COALESCE(MAX(rate), 0) AS max_rate FROM (
    SELECT COUNT(*) AS rate
    FROM muon_events
    WHERE ts >= ?
    GROUP BY strftime('%Y-%m-%d %H:%M', datetime(ts, 'unixepoch'))
)
"""


@router.get("/stats/today")
def get_stats_today() -> dict[str, Any]:
    """Return daily aggregate statistics for the current UTC day.

    Response shape::

        {
            "date": "YYYY-MM-DD",
            "muon_event_count": int,
            "weather_reading_count": int,
            "earthquake_count_by_source": {"usgs": int, "emsc": int, "bgs": int},
            "space_weather_reading_count": int,
            "lightning_strike_count": int,
            "aurora_reading_count": int,
            "max_muon_rate_per_min": int,
            "max_kp_index": float | None,       # rounded 2dp
            "max_pressure_hpa": float | None,   # rounded 2dp
            "min_pressure_hpa": float | None    # rounded 2dp
        }

    All counts are 0 for an empty DB; max/min values are None.
    earthquake_count_by_source always has all three source keys.
    """
    now = int(time.time())
    today_start = now - (now % 86400)
    today_str = datetime.fromtimestamp(today_start, tz=UTC).date().isoformat()

    with get_conn() as conn:
        muon_event_count: int = conn.execute(
            "SELECT COUNT(*) FROM muon_events WHERE ts >= ?", (today_start,)
        ).fetchone()[0]

        weather_reading_count: int = conn.execute(
            "SELECT COUNT(*) FROM weather WHERE ts >= ?", (today_start,)
        ).fetchone()[0]

        # Earthquake counts grouped by source — build a full dict with 0 defaults
        eq_rows = conn.execute(
            "SELECT source, COUNT(*) AS cnt FROM earthquakes WHERE ts >= ? GROUP BY source",
            (today_start,),
        ).fetchall()
        earthquake_count_by_source: dict[str, int] = {"usgs": 0, "emsc": 0, "bgs": 0}
        for row in eq_rows:
            if row["source"] in earthquake_count_by_source:
                earthquake_count_by_source[row["source"]] = row["cnt"]

        space_weather_reading_count: int = conn.execute(
            "SELECT COUNT(*) FROM space_weather WHERE ts >= ?", (today_start,)
        ).fetchone()[0]

        lightning_strike_count: int = conn.execute(
            "SELECT COUNT(*) FROM lightning_strikes WHERE ts >= ?", (today_start,)
        ).fetchone()[0]

        aurora_reading_count: int = conn.execute(
            "SELECT COUNT(*) FROM aurora_status WHERE ts >= ?", (today_start,)
        ).fetchone()[0]

        max_muon_rate_per_min: int = conn.execute(_MUON_RATE_SQL, (today_start,)).fetchone()[0]

        raw_max_kp: float | None = conn.execute(
            "SELECT MAX(kp_index) FROM space_weather WHERE ts >= ?", (today_start,)
        ).fetchone()[0]

        pressure_row = conn.execute(
            "SELECT MAX(pressure_hpa), MIN(pressure_hpa) FROM weather WHERE ts >= ?",
            (today_start,),
        ).fetchone()
        raw_max_pressure = pressure_row[0]
        raw_min_pressure = pressure_row[1]

    return {
        "date": today_str,
        "muon_event_count": muon_event_count,
        "weather_reading_count": weather_reading_count,
        "earthquake_count_by_source": earthquake_count_by_source,
        "space_weather_reading_count": space_weather_reading_count,
        "lightning_strike_count": lightning_strike_count,
        "aurora_reading_count": aurora_reading_count,
        "max_muon_rate_per_min": max_muon_rate_per_min,
        "max_kp_index": round(raw_max_kp, 2) if raw_max_kp is not None else None,
        "max_pressure_hpa": (round(raw_max_pressure, 2) if raw_max_pressure is not None else None),
        "min_pressure_hpa": (round(raw_min_pressure, 2) if raw_min_pressure is not None else None),
    }
