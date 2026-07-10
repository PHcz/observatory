"""Phase 15 — GET /api/indoor/* (read half for the indoor-air dashboard panel).

LOCAL-FIRST: reads only the ``indoor_air`` table (written by
``observatory.indoor.subscriber``); never touches MQTT or any upstream.

Endpoints:
    GET /api/indoor/current            -> latest reading per node + age
    GET /api/indoor/history?hours&node -> time series for the chart

Empty state: when no reading exists yet both endpoints return a valid 200 body
(``{"nodes": []}`` / ``{"rows": []}``) so the panel renders its empty state
rather than erroring.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Query

from observatory.db.connection import get_conn

router = APIRouter()

_CURRENT_COLS = ("node_id", "ts", "temp_c", "humidity_pct", "pressure_hpa", "co2_ppm")


@router.get("/indoor/current")
def get_indoor_current() -> dict[str, Any]:
    """Latest ``indoor_air`` row per node, each with its age in seconds."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT node_id, ts, temp_c, humidity_pct, pressure_hpa, co2_ppm "
            "FROM indoor_air "
            "WHERE id IN (SELECT MAX(id) FROM indoor_air GROUP BY node_id) "
            "ORDER BY node_id"
        ).fetchall()

    now = int(time.time())
    nodes = [{**{c: r[c] for c in _CURRENT_COLS}, "age_sec": now - int(r["ts"])} for r in rows]
    return {"nodes": nodes, "ts": now}


@router.get("/indoor/history")
def get_indoor_history(
    hours: int = Query(default=24, ge=1, le=168),
    node: str | None = Query(default=None),
) -> dict[str, Any]:
    """Indoor time series over the last ``hours`` (optionally one ``node``)."""
    now = int(time.time())
    frm = now - hours * 3600

    query = (
        "SELECT ts, node_id, co2_ppm, temp_c, humidity_pct, pressure_hpa "
        "FROM indoor_air WHERE ts >= ?"
    )
    params: list[Any] = [frm]
    if node:
        query += " AND node_id = ?"
        params.append(node)
    query += " ORDER BY ts ASC"

    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()

    return {
        "from": frm,
        "to": now,
        "hours": hours,
        "node": node,
        "rows": [dict(r) for r in rows],
    }
