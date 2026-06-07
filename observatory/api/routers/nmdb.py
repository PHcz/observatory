"""Phase 13 — GET /api/nmdb (MU2-06 read half).

Serves the cached NMDB neutron-monitor counts alongside the local muon flux, BOTH
normalised to % of their own median baseline on a SHARED 7-day time axis so a
Forbush dip lines up across both despite the very different absolute scales.

LOCAL-FIRST: this router NEVER touches any upstream API (no upstream HTTP client,
no upstream host) — only the poller (``observatory.pollers.nmdb``) makes the NEST
call. The read side
reads ``nmdb_counts`` + the ``nmdb_meta`` freshness anchor and bucket-aggregates
``muon_events`` into a wall-clock rate/min, then applies ``pct_of_baseline`` to
each series.

Local muon rate is WALL-CLOCK count/min (count / 60 minutes per hourly bucket) and
is explicitly raw — NOT dead-time corrected (``muon_events`` has no dead-time
field; the offline CLI stays the corrected source of truth).

Empty-state contract (mirrors forecast/air_quality): no NMDB data yet -> 200 with
``series=[]`` and ``fetched_at=null`` so the panel renders its locked empty state
rather than erroring.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter

from observatory.api._baseline import BASELINE_WINDOW_DAYS, pct_of_baseline
from observatory.db.connection import get_conn

router = APIRouter()

_WINDOW_SEC = BASELINE_WINDOW_DAYS * 86400
_BUCKET_SEC = 3600  # hourly buckets for the local muon rate (shared axis with NMDB)


def _local_muon_series(conn: Any, frm: int, to: int) -> list[dict[str, Any]]:
    """Bucket muon_events into hourly wall-clock rate/min over [frm, to)."""
    rows = conn.execute(
        "SELECT (ts / ?) * ? AS bucket_ts, COUNT(*) AS n "
        "FROM muon_events WHERE ts BETWEEN ? AND ? "
        "GROUP BY bucket_ts ORDER BY bucket_ts",
        (_BUCKET_SEC, _BUCKET_SEC, frm, to),
    ).fetchall()
    return [
        {"ts": int(r["bucket_ts"]), "rate_per_min": r["n"] / (_BUCKET_SEC / 60.0)} for r in rows
    ]


@router.get("/nmdb")
def get_nmdb() -> dict[str, Any]:
    """Return NMDB + local muon %-of-baseline series on a shared 7-day axis.

    Response shape::

        {
            "series": [{ts, counts_per_sec, pct_baseline}],   # NMDB (Oulu)
            "local":  [{ts, rate_per_min, pct_baseline}],     # raw wall-clock
            "baseline_window_days": 7,
            "fetched_at": int | null
        }

    Empty NMDB cache (no poll yet) -> empty-state 200 (``series=[]``,
    ``fetched_at=null``). LOCAL-FIRST: SQLite only, never upstream.
    """
    now = int(time.time())
    frm = now - _WINDOW_SEC

    with get_conn() as conn:
        meta = conn.execute("SELECT fetched_at FROM nmdb_meta WHERE id = 1").fetchone()
        nmdb_rows = conn.execute(
            "SELECT ts, counts_per_sec FROM nmdb_counts WHERE ts BETWEEN ? AND ? ORDER BY ts",
            (frm, now),
        ).fetchall()
        local_rows = _local_muon_series(conn, frm, now)

    fetched_at = meta["fetched_at"] if meta is not None else None

    if not nmdb_rows:
        # No NMDB data yet -> empty-but-valid body (UI-SPEC empty state). Still
        # surface any local series so the panel can show the home detector alone.
        local_vals = [r["rate_per_min"] for r in local_rows]
        local_pct = pct_of_baseline(local_vals)
        local_out = [
            {"ts": r["ts"], "rate_per_min": r["rate_per_min"], "pct_baseline": p}
            for r, p in zip(local_rows, local_pct, strict=True)
        ]
        return {
            "series": [],
            "local": local_out,
            "baseline_window_days": BASELINE_WINDOW_DAYS,
            "fetched_at": None,
        }

    nmdb_vals = [r["counts_per_sec"] for r in nmdb_rows]
    nmdb_pct = pct_of_baseline(nmdb_vals)
    series = [
        {"ts": r["ts"], "counts_per_sec": r["counts_per_sec"], "pct_baseline": p}
        for r, p in zip(nmdb_rows, nmdb_pct, strict=True)
    ]

    local_vals = [r["rate_per_min"] for r in local_rows]
    local_pct = pct_of_baseline(local_vals)
    local_out = [
        {"ts": r["ts"], "rate_per_min": r["rate_per_min"], "pct_baseline": p}
        for r, p in zip(local_rows, local_pct, strict=True)
    ]

    return {
        "series": series,
        "local": local_out,
        "baseline_window_days": BASELINE_WINDOW_DAYS,
        "fetched_at": fetched_at,
    }
