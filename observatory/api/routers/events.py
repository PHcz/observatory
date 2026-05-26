"""Phase 6 — /api/events/recent mixed event feed endpoint.

Implemented by Plan 06-04.

Design notes:
- UNION ALL across 6 data tables, each row tagged with a 'type' literal.
- muon_events are capped to the last 10 rows before the UNION to prevent the
  continuously-streaming muon data from drowning out all other event types in
  the 100-row limit.
- SQLite json_object() produces a JSON string; json.loads() parses it back so
  the 'data' field in the response is a structured dict, not a string.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter

from observatory.db.connection import get_conn

router = APIRouter()

# UNION ALL query — muon sub-query capped at 10 rows so the mixed feed shows variety.
# The outer ORDER BY ts DESC LIMIT 100 applies across all 6 sub-queries.
# nosec B608 — no user input is interpolated; all string literals are hardcoded.
_EVENTS_SQL = """
SELECT type, ts, data FROM (
    SELECT 'weather' AS type, ts,
           json_object(
               'temp_c', temp_c, 'humidity_pct', humidity_pct, 'pressure_hpa', pressure_hpa
           ) AS data
    FROM weather
    UNION ALL
    SELECT 'muon' AS type, ts,
           json_object('amplitude', amplitude, 'coincidence', coincidence) AS data
    FROM (SELECT ts, amplitude, coincidence FROM muon_events ORDER BY ts DESC LIMIT 10)
    UNION ALL
    SELECT 'earthquake' AS type, ts,
           json_object('source', source, 'magnitude', magnitude, 'place', place) AS data
    FROM earthquakes
    UNION ALL
    SELECT 'space_weather' AS type, ts,
           json_object('kp_index', kp_index, 'flare_class', flare_class) AS data
    FROM space_weather
    UNION ALL
    SELECT 'lightning' AS type, ts,
           json_object('distance_km', distance_km) AS data
    FROM lightning_strikes
    UNION ALL
    SELECT 'aurora' AS type, ts,
           json_object('status', status, 'detail', detail) AS data
    FROM aurora_status
)
ORDER BY ts DESC
LIMIT 100
"""  # nosec B608


@router.get("/events/recent")
def get_events_recent() -> dict[str, Any]:
    """Return the last 100 events across all 6 data sources, mixed and ordered.

    Response shape::

        {
            "rows": [
                {"type": str, "ts": int, "data": dict},
                ...
            ]
        }

    Notes:
        - muon_events contribution is capped at 10 rows before the UNION so the
          feed shows variety (muon data streams at ~1Hz; uncapped it would fill
          all 100 slots).
        - 'data' is always a dict (json.loads applied after SQLite json_object()).
    """
    with get_conn() as conn:
        rows: list[dict[str, Any]] = [
            {
                "type": row["type"],
                "ts": row["ts"],
                "data": json.loads(row["data"]),
            }
            for row in conn.execute(_EVENTS_SQL)
        ]

    return {"rows": rows}
