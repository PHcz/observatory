"""Phase 16 ENH-04: GET /api/alerts — active + recent alert list.

Returns:
    {
        "active": [AlertRow, ...],   -- resolved_at_ts IS NULL
        "recent": [AlertRow, ...]    -- resolved in the last 24 h
    }

Empty DB → 200 {"active": [], "recent": []}

AlertRow shape (matches alerts table):
    {
        "id": int,
        "rule": str,
        "severity": str,
        "crossed_at_ts": int,
        "resolved_at_ts": int | null,
        "detail_text": str
    }
"""

from __future__ import annotations

import time

import structlog
from fastapi import APIRouter

from observatory.db.connection import get_conn

log = structlog.get_logger(__name__)

router = APIRouter()


def _row_to_dict(row: object) -> dict:
    """Convert a sqlite3.Row to a plain dict for JSON serialisation."""
    return dict(row)  # type: ignore[arg-type]


@router.get("/alerts")
def get_alerts() -> dict:
    """Return active and recently-resolved alerts.

    active  — rows where resolved_at_ts IS NULL (still triggering)
    recent  — rows resolved within the last 24 hours

    Always returns 200, even on an empty DB.
    """
    now = int(time.time())
    since = now - 86400  # 24 h window for recent

    with get_conn() as conn:
        active_rows = conn.execute(
            "SELECT id, rule, severity, crossed_at_ts, resolved_at_ts, detail_text"
            " FROM alerts"
            " WHERE resolved_at_ts IS NULL"
            " ORDER BY crossed_at_ts DESC",
        ).fetchall()

        recent_rows = conn.execute(
            "SELECT id, rule, severity, crossed_at_ts, resolved_at_ts, detail_text"
            " FROM alerts"
            " WHERE resolved_at_ts IS NOT NULL"
            "   AND resolved_at_ts >= ?"
            " ORDER BY resolved_at_ts DESC",
            (since,),
        ).fetchall()

    return {
        "active": [_row_to_dict(r) for r in active_rows],
        "recent": [_row_to_dict(r) for r in recent_rows],
    }
