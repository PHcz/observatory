"""Phase 13 — GET /api/forbush (MU2-07 Forbush-decrease indicator).

Surfaces a calm-by-default Forbush status chip driven by the reliable global
neutron-monitor reference (NMDB / Oulu) plus NOAA space weather, avoiding false
alarms from the small home detector. The classification itself is the pure
``classify_forbush`` state machine; this router only gathers its inputs from
SQLite and hands them over.

LOCAL-FIRST: SQLite only — this router NEVER touches any upstream API (only the
NMDB poller makes the NEST call). It reads ``nmdb_counts`` (+ ``nmdb_meta``),
``space_weather`` and ``muon_events``, reusing ``pct_of_baseline`` for the
recent-vs-median drop of both the NMDB and the local muon series.

The "drop" for each series is ``100 - recent_pct`` where ``recent_pct`` is the
mean %-of-baseline over the most-recent ``RECENT_WINDOW_SEC`` (research §Forbush),
the baseline being the median over the trailing ``BASELINE_WINDOW_DAYS`` window.

Empty-state contract (mirrors nmdb/forecast/air_quality): no ``nmdb_counts`` data
-> 200 with the Quiet state and the locked awaiting-data detail line (NOT 404).
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter

from observatory.api._baseline import BASELINE_WINDOW_DAYS, pct_of_baseline
from observatory.api._forbush import RECENT_WINDOW_SEC, classify_forbush
from observatory.db.connection import get_conn

router = APIRouter()

_WINDOW_SEC = BASELINE_WINDOW_DAYS * 86400
_BUCKET_SEC = 3600  # hourly buckets for the local muon wall-clock rate


def _recent_drop_pct(series: list[tuple[int, float | None]], recent_from: int) -> float | None:
    """Recent %-baseline drop for a (ts, value) series.

    Baseline = median over the whole window; ``recent_pct`` = mean %-baseline over
    rows at/after ``recent_from``; drop = ``100 - recent_pct``. Returns ``None``
    when there is no usable data (no baseline, or no recent rows).
    """
    if not series:
        return None
    pct = pct_of_baseline([v for _ts, v in series])
    recent = [
        p for (ts, _v), p in zip(series, pct, strict=True) if ts >= recent_from and p is not None
    ]
    if not recent:
        return None
    recent_pct = sum(recent) / len(recent)
    return 100.0 - recent_pct


@router.get("/forbush")
def get_forbush() -> dict[str, Any]:
    """Return the Forbush state plus the inputs that drove it.

    Response shape::

        {
            "state": "quiet" | "watch" | "forbush",
            "nmdb_drop_pct": float | null,
            "kp": float | null,
            "solar_wind_kms": float | null,
            "local_drop_pct": float | null,
            "detail": str
        }

    Empty NMDB cache -> Quiet empty-state 200 with the locked detail line.
    LOCAL-FIRST: SQLite only, never upstream.
    """
    now = int(time.time())
    frm = now - _WINDOW_SEC
    recent_from = now - RECENT_WINDOW_SEC

    with get_conn() as conn:
        nmdb_rows = conn.execute(
            "SELECT ts, counts_per_sec FROM nmdb_counts WHERE ts BETWEEN ? AND ? ORDER BY ts",
            (frm, now),
        ).fetchall()
        sw = conn.execute(
            "SELECT kp_index, solar_wind_kms FROM space_weather ORDER BY ts DESC LIMIT 1"
        ).fetchone()
        local_rows = conn.execute(
            "SELECT (ts / ?) * ? AS bucket_ts, COUNT(*) AS n "
            "FROM muon_events WHERE ts BETWEEN ? AND ? "
            "GROUP BY bucket_ts ORDER BY bucket_ts",
            (_BUCKET_SEC, _BUCKET_SEC, frm, now),
        ).fetchall()

    kp = sw["kp_index"] if sw is not None else None
    solar_wind_kms = sw["solar_wind_kms"] if sw is not None else None

    # NMDB primary signal: recent-vs-median drop. Absent -> None (state machine
    # collapses to Quiet with the locked detail line).
    nmdb_series: list[tuple[int, float | None]] = [
        (int(r["ts"]), r["counts_per_sec"]) for r in nmdb_rows
    ]
    nmdb_drop_pct = _recent_drop_pct(nmdb_series, recent_from) if nmdb_series else None

    # Local secondary signal: wall-clock rate/min per hourly bucket (confirm-only).
    local_series: list[tuple[int, float | None]] = [
        (int(r["bucket_ts"]), r["n"] / (_BUCKET_SEC / 60.0)) for r in local_rows
    ]
    local_drop_pct = _recent_drop_pct(local_series, recent_from) if local_series else None

    result = classify_forbush(
        nmdb_drop_pct=nmdb_drop_pct,
        kp=kp,
        solar_wind_kms=solar_wind_kms,
        local_drop_pct=local_drop_pct,
    )

    return {
        "state": result["state"],
        "nmdb_drop_pct": nmdb_drop_pct,
        "kp": kp,
        "solar_wind_kms": solar_wind_kms,
        "local_drop_pct": local_drop_pct,
        "detail": result["detail"],
    }
