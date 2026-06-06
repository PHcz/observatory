"""Phase 10 — GET /api/forecast (FCAST-02 read half + FCAST-04 vs-actual).

Serves the cached forecast from SQLite and computes forecast-vs-actual
server-side. LOCAL-FIRST: this router NEVER touches any upstream weather API —
only the poller (``observatory.pollers.forecast``) makes the upstream call. The
read side reads
``forecast_hourly`` / ``forecast_daily`` / ``forecast_meta`` and joins today's
forecast against measured ``weather`` rows over the HOME-TIMEZONE local day.

Empty-state contract (10-RESEARCH Pattern 2 — diverges from the aurora/current
404 idiom): when no forecast has been polled yet the endpoint returns a valid
200 body ``{"hourly": [], "daily": [], "vs_actual": null, "fetched_at": null}``
so the panel can render its locked empty state instead of an error.

Local-day boundary (10-RESEARCH Pitfall 4): vs-actual uses
``forecast_daily.ts[0]`` — already the local-day start as a UTC epoch (carved
out by the poller's stored ``utc_offset_seconds``). It deliberately does NOT
reuse the ``stats/today`` UTC-day math (``now - now % 86400``), which diverges
from the local day by the UTC offset (1h in BST). Do not "fix" stats here.
"""

from __future__ import annotations

import sqlite3
import time
from typing import Any

from fastapi import APIRouter

from observatory.db.connection import get_conn

router = APIRouter()

# vs-actual temperature thresholds (°C):
#   |Δ| < ON_TRACK_BAND  -> "on_track"
#   else                 -> "cool" (actual cooler) / "warm" (actual warmer)
#   |Δ| >= WARN_THRESHOLD -> warn tint (UI-SPEC)
_ON_TRACK_BAND_C = 1.0
_WARN_THRESHOLD_C = 3.0

_DAY_SECONDS = 86400


def _temp_metric(
    forecast: float | None, actual: float | None, *, warn_threshold_c: float
) -> dict[str, Any]:
    """Build a {forecast, actual, delta, label, warn} block for one temp metric.

    ``delta = actual - forecast`` (signed): negative -> actual cooler than
    forecast, positive -> warmer. Degrades to actual=null/delta=null/label=null
    when no measured value exists (empty weather for today — Pitfall 5).
    """
    if forecast is None or actual is None:
        return {"forecast": forecast, "actual": actual, "delta": None, "label": None, "warn": False}
    delta = round(actual - forecast, 1)
    if abs(delta) < _ON_TRACK_BAND_C:
        label = "on_track"
    elif delta < 0:
        label = "cool"
    else:
        label = "warm"
    return {
        "forecast": forecast,
        "actual": actual,
        "delta": delta,
        "label": label,
        "warn": abs(delta) >= warn_threshold_c,
    }


def compute_vs_actual(
    today_forecast: dict[str, Any] | None,
    forecast_means: dict[str, Any],
    actual: dict[str, Any],
    *,
    warn_threshold_c: float = _WARN_THRESHOLD_C,
) -> dict[str, Any] | None:
    """Reduce today's forecast vs measured actuals into the vs-actual block.

    Pure + unit-testable: callers feed it the today daily row, the today
    hourly forecast means (humidity/pressure), and the today actual weather
    aggregate. Returns ``None`` when there is no daily forecast row at all.

    Temp: forecast daily high/low vs measured MAX/MIN -> signed delta +
        cool/warm/on_track label + warn flag (|Δ| >= warn_threshold_c).
    Humidity/pressure: forecast (today hourly mean) vs measured (today mean),
        plain values, NO verb/label (UI-SPEC).
    Precip: info-only — today's forecast precip_prob_max, never a comparison.
    Degrade: any NULL actual -> that metric's actual=null, still returns a body.
    """
    if today_forecast is None:
        return None

    amin = actual.get("amin")
    amax = actual.get("amax")
    ahum = actual.get("ahum")
    apres = actual.get("apres")

    high = _temp_metric(today_forecast.get("temp_max_c"), amax, warn_threshold_c=warn_threshold_c)
    low = _temp_metric(today_forecast.get("temp_min_c"), amin, warn_threshold_c=warn_threshold_c)

    fhum = forecast_means.get("fhum")
    fpres = forecast_means.get("fpres")

    return {
        # The panel renders the UI-SPEC strings from these structured fields.
        # `temp` carries both high and low blocks; tests inspect str(temp) for
        # the cool label and ensure out-of-window readings never appear.
        "temp": {"high": high, "low": low, "actual": amax},
        "humidity": {
            "forecast": round(fhum) if fhum is not None else None,
            "actual": round(ahum) if ahum is not None else None,
        },
        "pressure": {
            "forecast": round(fpres, 1) if fpres is not None else None,
            "actual": round(apres, 1) if apres is not None else None,
        },
        "precip": {"prob_max": today_forecast.get("precip_prob_max_pct")},
    }


def _build_vs_actual(conn: sqlite3.Connection) -> dict[str, Any] | None:
    """Read today's forecast + measured actuals from SQLite and reduce.

    The local-day window is ``[local_day_start, local_day_start + 86400)`` where
    ``local_day_start`` is the FIRST forecast_daily row's ts (already the
    local-day start as a UTC epoch — the poller carved it out via
    utc_offset_seconds). This is INTENTIONALLY not the stats/today UTC day.
    """
    today_row = conn.execute(
        """
        SELECT ts, temp_max_c, temp_min_c, precip_prob_max_pct
        FROM forecast_daily
        ORDER BY ts ASC
        LIMIT 1
        """
    ).fetchone()
    if today_row is None:
        return None

    local_day_start = int(today_row["ts"])
    local_day_end = local_day_start + _DAY_SECONDS

    today_forecast = {
        "temp_max_c": today_row["temp_max_c"],
        "temp_min_c": today_row["temp_min_c"],
        "precip_prob_max_pct": today_row["precip_prob_max_pct"],
    }

    # Forecast humidity/pressure for today = MEAN of today's hourly rows
    # (Open Question 1: the locked daily set has no humidity/pressure, so the
    # forecast side is sourced from the extra hourly columns added in 10-01/02).
    fmeans = conn.execute(
        """
        SELECT AVG(relative_humidity_pct) AS fhum,
               AVG(surface_pressure_hpa) AS fpres
        FROM forecast_hourly
        WHERE ts >= ? AND ts < ?
        """,
        (local_day_start, local_day_end),
    ).fetchone()
    forecast_means = {
        "fhum": fmeans["fhum"] if fmeans is not None else None,
        "fpres": fmeans["fpres"] if fmeans is not None else None,
    }

    # Measured actuals over the SAME local-day window (NOT a UTC-day boundary —
    # stats/today uses UTC day and diverges by the offset; see module docstring).
    actual_row = conn.execute(
        """
        SELECT MIN(temp_c) AS amin,
               MAX(temp_c) AS amax,
               AVG(humidity_pct) AS ahum,
               AVG(pressure_hpa) AS apres
        FROM weather
        WHERE ts >= ? AND ts < ?
        """,
        (local_day_start, local_day_end),
    ).fetchone()
    actual = {
        "amin": actual_row["amin"] if actual_row is not None else None,
        "amax": actual_row["amax"] if actual_row is not None else None,
        "ahum": actual_row["ahum"] if actual_row is not None else None,
        "apres": actual_row["apres"] if actual_row is not None else None,
    }

    return compute_vs_actual(today_forecast, forecast_means, actual)


@router.get("/forecast")
def get_forecast() -> dict[str, Any]:
    """Return the cached forecast: next-24h hourly + 7 daily + vs-actual.

    Response shape::

        {
            "hourly": [{ts, temp_c, apparent_temp_c, relative_humidity_pct,
                        surface_pressure_hpa, precip_prob_pct, weather_code,
                        wind_speed_kmh}, ...],   # next 24h relative to now
            "daily":  [{ts, temp_max_c, temp_min_c, precip_prob_max_pct,
                        weather_code, wind_speed_max_kmh}, ...],  # 7 rows
            "vs_actual": {...} | null,
            "fetched_at": int | null
        }

    Empty forecast tables -> empty-state 200 body (NOT 404) so the panel shows
    its locked empty state. LOCAL-FIRST: SQLite only, never an upstream call.
    """
    now = int(time.time())

    with get_conn() as conn:
        meta = conn.execute(
            "SELECT fetched_at, utc_offset_seconds, timezone FROM forecast_meta WHERE id = 1"
        ).fetchone()
        if meta is None:
            # No poll has run yet -> empty-but-valid body (UI-SPEC empty state).
            return {"hourly": [], "daily": [], "vs_actual": None, "fetched_at": None}

        # Next-24h hourly window relative to NOW (Pitfall 3: not array index 0,
        # which is local midnight). Store-all / slice-on-read.
        hourly_rows = conn.execute(
            """
            SELECT ts, temp_c, apparent_temp_c, relative_humidity_pct,
                   surface_pressure_hpa, precip_prob_pct, weather_code, wind_speed_kmh
            FROM forecast_hourly
            WHERE ts >= ?
            ORDER BY ts ASC
            LIMIT 24
            """,
            (now,),
        ).fetchall()

        daily_rows = conn.execute(
            """
            SELECT ts, temp_max_c, temp_min_c, precip_prob_max_pct,
                   weather_code, wind_speed_max_kmh
            FROM forecast_daily
            ORDER BY ts ASC
            """
        ).fetchall()

        vs_actual = _build_vs_actual(conn)

    return {
        "hourly": [dict(r) for r in hourly_rows],
        "daily": [dict(r) for r in daily_rows],
        "vs_actual": vs_actual,
        "fetched_at": meta["fetched_at"],
    }
