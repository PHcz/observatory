"""Phase 6 — /api/muon time-series endpoint.

Implemented by Plan 06-03. Provides bucketed muon event counts from the local
SQLite store with agg=auto|raw|minute|hour|day query support.

rate_per_min derivation:
    For bucketed aggregations, COUNT(*) events per bucket is stored as event_count.
    rate_per_min = event_count * 60 / BUCKET_SECONDS[resolved], rounded to 2 dp.
    This field is ABSENT for raw agg rows — do not include a null; omit it entirely
    (documented in 06-03-SUMMARY.md for Phase 7 frontend handling).
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from observatory.api._serializers import (
    BUCKET_SECONDS,
    BUCKET_SQL_STRFTIME,
    DEFAULT_WINDOW_SEC,
    MAX_ROWS,
    AggLiteral,
    TimeSeriesResponse,
    resolve_agg,
)
from observatory.db.connection import get_conn
from observatory.muon.pressure import stp_corrected_rate

router = APIRouter()


@router.get("/muon", response_model=TimeSeriesResponse)
def get_muon(
    from_: int | None = Query(default=None, alias="from", ge=0),
    to: int | None = Query(default=None, ge=0),
    agg: AggLiteral = Query(default="auto"),  # noqa: B008
) -> TimeSeriesResponse:
    """Return muon event time-series for the requested window.

    Query params:
        from: epoch-seconds start (default: now - 86400)
        to:   epoch-seconds end   (default: now)
        agg:  raw | minute | hour | day | auto (default: auto)

    Response shape:
        {"window": {"from": int, "to": int}, "bucket_size_sec": int, "agg": str, "rows": [...]}

    Raw rows: ts, detector_pressure_hpa, detector_temp_c, amplitude, coincidence (integer).
    Bucketed rows: ts, event_count, rate_per_min, detector_pressure_hpa, detector_temp_c, amplitude.
    Note: rate_per_min is ABSENT (not null) in raw rows.
    """
    now = int(time.time())
    to = to if to is not None else now
    from_ = from_ if from_ is not None else (to - DEFAULT_WINDOW_SEC)

    if from_ >= to:
        raise HTTPException(status_code=422, detail="from must be < to")

    window_sec = to - from_
    resolved = resolve_agg(window_sec, agg)
    bucket_sec = BUCKET_SECONDS[resolved]

    with get_conn() as conn:
        if resolved == "raw":
            cursor = conn.execute(
                """
                SELECT ts, detector_pressure_hpa, detector_temp_c, amplitude, coincidence
                FROM muon_events
                WHERE ts BETWEEN ? AND ?
                ORDER BY ts ASC
                LIMIT ?
                """,
                (from_, to, MAX_ROWS),
            )
            rows = [dict(r) for r in cursor]
        else:
            # Bucket template comes from whitelist — no user input interpolated.
            # nosec B608
            bucket_expr = BUCKET_SQL_STRFTIME[resolved]
            cursor = conn.execute(
                f"""
                SELECT MIN(ts) AS ts,
                       COUNT(*) AS event_count,
                       AVG(detector_pressure_hpa) AS detector_pressure_hpa,
                       AVG(detector_temp_c) AS detector_temp_c,
                       AVG(amplitude) AS amplitude
                FROM muon_events
                WHERE ts BETWEEN ? AND ?
                GROUP BY {bucket_expr}
                ORDER BY ts ASC
                LIMIT ?
                """,  # nosec B608
                (from_, to, MAX_ROWS),
            )
            raw_rows = [dict(r) for r in cursor]
            rows = []
            for r in raw_rows:
                event_count: int = r["event_count"]
                raw_rate = event_count * 60 / bucket_sec
                # UKRAA STP pressure correction (see observatory.muon.pressure):
                # normalize the rate to 20 degC / 1013.25 hPa using the bucket's
                # mean detector temp + pressure. Unchanged when either is missing.
                corrected = stp_corrected_rate(
                    raw_rate, r["detector_temp_c"], r["detector_pressure_hpa"]
                )
                rate_per_min = round(corrected if corrected is not None else raw_rate, 2)
                rows.append(
                    {
                        "ts": r["ts"],
                        "event_count": event_count,
                        "rate_per_min": rate_per_min,
                        "detector_pressure_hpa": (
                            round(r["detector_pressure_hpa"], 2)
                            if r["detector_pressure_hpa"] is not None
                            else None
                        ),
                        "detector_temp_c": (
                            round(r["detector_temp_c"], 2)
                            if r["detector_temp_c"] is not None
                            else None
                        ),
                        "amplitude": (
                            round(r["amplitude"], 4) if r["amplitude"] is not None else None
                        ),
                    }
                )

    return TimeSeriesResponse(
        window={"from": from_, "to": to},
        bucket_size_sec=bucket_sec,
        agg=resolved,
        rows=rows,
    )


# --- Phase 13 (MU2-05): live muon-analysis panels -------------------------------

_ANALYSIS_WINDOW_DAYS = 7
_ANALYSIS_WINDOW_SEC = _ANALYSIS_WINDOW_DAYS * 86400


def _empty_analysis(frm: int, to: int, *, analysis_available: bool = True) -> dict[str, Any]:
    """Empty-state body for /api/muon/analysis (200, never 404/500)."""
    return {
        "adc_histogram": [],
        "barometric": None,
        "window": {"from": frm, "to": to, "days": _ANALYSIS_WINDOW_DAYS},
        "raw_uncorrected": True,
        "analysis_available": analysis_available,
    }


@router.get("/muon/analysis")
def get_muon_analysis() -> dict[str, Any]:
    """Live ADC histogram + barometric coefficient over a rolling 7-day window.

    Computed on-request from ``muon_events`` (SQLite only — LOCAL-FIRST, never
    upstream) via ``observatory.muon.analysis_adapter``, which reuses the
    Phase-12 ``picomuon`` core. The live rate is RAW wall-clock count/bucket
    with NO dead-time correction (``raw_uncorrected: true`` — the honesty line);
    the offline CLI stays the dead-time-corrected source of truth.

    Response shape::

        {
            "adc_histogram": [{"bin_center": float, "count": int}, ...],
            "barometric": {"beta", "r_squared", "p_value", "n",
                           "points": [{"pressure_hpa", "rate_per_min"}, ...]} | null,
            "window": {"from": int, "to": int, "days": 7},
            "raw_uncorrected": true,
            "analysis_available": bool
        }

    Empty / thin data -> empty-state 200 (NOT 404/500). If the ``[analysis]``
    extra (polars/scipy via picomuon) is missing from the API venv, the lazy
    import fails and the route degrades to an empty-state 200 with
    ``analysis_available: false`` rather than a 500 (Pitfall 7).
    """
    now = int(time.time())
    frm = now - _ANALYSIS_WINDOW_SEC

    # Lazy-import the analysis stack so a missing [analysis] extra degrades to an
    # empty-state 200 rather than taking down the rest of the API on import.
    try:
        from observatory.muon.analysis_adapter import (
            live_adc_histogram,
            live_barometric,
            live_barometric_points,
        )
    except ImportError:
        return _empty_analysis(frm, now, analysis_available=False)

    with get_conn() as conn:
        cursor = conn.execute(
            """
            SELECT ts, amplitude, detector_pressure_hpa
            FROM muon_events
            WHERE ts BETWEEN ? AND ? AND coincidence = 1
            ORDER BY ts ASC
            """,
            (frm, now),
        )
        rows = [(r["ts"], r["amplitude"], r["detector_pressure_hpa"], 1) for r in cursor]

    if not rows:
        return _empty_analysis(frm, now)

    hist = live_adc_histogram(rows)
    adc_histogram_out = [
        {"bin_center": bc, "count": c}
        for bc, c in zip(hist["bin_center"].to_list(), hist["count"].to_list(), strict=True)
    ]

    fit = live_barometric(rows)
    barometric_out: dict[str, Any] | None
    if fit is None:
        barometric_out = None
    else:
        # Points use the same thin-data gate as the fit, so they're a non-empty
        # list whenever barometric is non-null and [] otherwise.
        barometric_out = {
            "beta": fit.beta,
            "r_squared": fit.r_squared,
            "p_value": fit.p_value,
            "n": fit.n,
            "points": live_barometric_points(rows),
        }

    return {
        "adc_histogram": adc_histogram_out,
        "barometric": barometric_out,
        "window": {"from": frm, "to": now, "days": _ANALYSIS_WINDOW_DAYS},
        "raw_uncorrected": True,
        "analysis_available": True,
    }
