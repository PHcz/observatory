"""Phase 6 — /api/aurora/current snapshot endpoint.

Implemented by Plan 06-04.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from observatory.db.connection import get_conn

router = APIRouter()


@router.get("/aurora/current")
def get_aurora_current() -> dict[str, Any]:
    """Return the latest aurora_status row.

    Response shape::

        {"ts": int, "status": str, "detail": str | None}

    Raises 404 if no aurora_status rows exist.
    """
    with get_conn() as conn:
        row = conn.execute(
            "SELECT ts, status, detail FROM aurora_status ORDER BY ts DESC LIMIT 1"
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="No aurora_status rows yet")

    return dict(row)
