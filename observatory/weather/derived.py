"""Phase 16 ENH-05: Weather derived metrics computed read-time in FastAPI.

NO new SQLite columns — all functions operate on values already in the DB
and return computed metrics at request time.

Functions:
    station_to_mslp    — reduce station pressure to mean sea-level pressure
    classify_tendency  — classify 3h pressure tendency as rising/steady/falling
    zambretti_z        — Zambretti Z score (1-26) from MSLP + tendency
    ZAMBRETTI_FORECAST — 26-entry dict mapping Z → plain-English forecast
    heat_index_c       — Rothfusz heat index (feels-like temp from temp+humidity)
    dewpoint_c         — simplified Magnus dewpoint (temp - (100-rh)/5)
    local_midnight_ts  — UTC epoch of local midnight in the configured timezone
    today_so_far       — query helper returning today's weather summary stats
"""

from __future__ import annotations

import datetime
import sqlite3
import zoneinfo
from typing import Any

# ---------------------------------------------------------------------------
# MSLP reduction
# ---------------------------------------------------------------------------


def station_to_mslp(
    pressure_hpa: float,
    altitude_m: float,
    temp_c: float,
) -> float:
    """Reduce station pressure to MSLP (hPa) using standard barometric formula.

    Uses the hypsometric equation with standard temperature lapse rate
    (International Standard Atmosphere lapse rate 0.0065 K/m).
    Accurate within ~1 hPa for altitudes < 1000 m and temp -20 to +40 C.

    When altitude_m == 0 the formula reduces to: MSLP = station_pressure * 1^5.2561
    which equals station_pressure exactly.

    Source: WeeWX / METAR standard barometric reduction.
    """
    T_K = temp_c + 273.15
    exponent = 5.2561
    return pressure_hpa * (1.0 + (0.0065 * altitude_m) / T_K) ** exponent


# ---------------------------------------------------------------------------
# Pressure tendency classification
# ---------------------------------------------------------------------------


def classify_tendency(delta_hpa_per_3h: float) -> str:
    """Classify 3h pressure change into rising / steady / falling.

    Thresholds from w4krl.com / sassoftware Zambretti implementation:
        > +1.6 hPa  → "rising"
        < -1.6 hPa  → "falling"
        otherwise   → "steady"
    """
    if delta_hpa_per_3h > 1.6:
        return "rising"
    if delta_hpa_per_3h < -1.6:
        return "falling"
    return "steady"


# ---------------------------------------------------------------------------
# Zambretti forecaster
# ---------------------------------------------------------------------------

# Full 26-entry Northern Hemisphere table (Z → plain-English forecast).
# Source: sassoftware/iot-zambretti-weather-forcasting + w4krl.com.
# The simplified 26-code table is the industry standard for anemometer-less
# stations (WeeWX, weewx-zambretti, etc.).
ZAMBRETTI_FORECAST: dict[int, str] = {
    1: "Settled Fine",
    2: "Fine Weather",
    3: "Fine, Becoming Less Settled",
    4: "Fairly Fine, Showery Later",
    5: "Showery, Becoming More Unsettled",
    6: "Unsettled, Rain Later",
    7: "Rain at Times, Worse Later",
    8: "Rain at Times, Becoming Very Unsettled",
    9: "Very Unsettled, Rain",
    10: "Settled Fine",
    11: "Fine Weather",
    12: "Fine, Possibly Showers",
    13: "Fairly Fine, Showers Likely",
    14: "Showery, Bright Intervals",
    15: "Changeable, Some Rain",
    16: "Unsettled, Rain at Times",
    17: "Rain at Frequent Intervals",
    18: "Very Unsettled, Rain",
    19: "Stormy, Much Rain",
    20: "Settled Fine",
    21: "Fine Weather",
    22: "Becoming Fine",
    23: "Fairly Fine, Improving",
    24: "Fairly Fine, Possibly Showers Early",
    25: "Showery Early, Improving",
    26: "Changeable, Mending",
}


def zambretti_z(mslp_hpa: float, tendency: str) -> int:
    """Compute Zambretti Z score (1-26) from MSLP + tendency direction.

    Operates on MSLP (NOT raw station pressure) — Zambretti is calibrated
    against sea-level pressure (Pitfall 2 from RESEARCH.md).

    Args:
        mslp_hpa: Mean sea-level pressure in hPa (from station_to_mslp).
        tendency: "rising" | "steady" | "falling" (from classify_tendency).

    Returns:
        Integer Z in [1..26] clamped to the valid Northern Hemisphere range.
    """
    if tendency == "falling":
        z = round(130 - 0.12 * mslp_hpa)
    elif tendency == "steady":
        z = round(147 - 0.13 * mslp_hpa)
    else:  # rising
        z = round(179 - 0.16 * mslp_hpa)
    return max(1, min(26, z))


# ---------------------------------------------------------------------------
# Feels-like / dewpoint
# ---------------------------------------------------------------------------


def heat_index_c(temp_c: float, humidity_pct: float) -> float:
    """Steadman / NWS Rothfusz heat index approximation.

    Returns temp_c unchanged when not in the heat-stress regime:
        - temp_c < 26.7 C  (below 80 F)
        - humidity_pct < 40 %

    Source: NWS Rothfusz regression polynomial.
    """
    if temp_c < 26.7 or humidity_pct < 40.0:
        return temp_c
    T = temp_c
    R = humidity_pct
    hi = (
        -8.78469475556
        + 1.61139411 * T
        + 2.33854883889 * R
        - 0.14611605 * T * R
        - 0.012308094 * T**2
        - 0.0164248277778 * R**2
        + 0.002211732 * T**2 * R
        + 0.00072546 * T * R**2
        - 0.000003582 * T**2 * R**2
    )
    return hi


def dewpoint_c(temp_c: float, humidity_pct: float) -> float:
    """Simplified Magnus dewpoint formula: T_d = T - (100 - RH) / 5.

    Accurate to ~1 C over 0-50 C / 40-100% RH.
    At 100% humidity dewpoint == air temperature.
    """
    return temp_c - (100.0 - humidity_pct) / 5.0


# ---------------------------------------------------------------------------
# Local midnight helper
# ---------------------------------------------------------------------------


def local_midnight_ts(
    tz_name: str,
    now: datetime.datetime | None = None,
) -> int:
    """Return UTC epoch seconds for local midnight in the given IANA timezone.

    Avoids the Pitfall 3 trap: SQLite ts values are UTC epoch seconds.
    'Since midnight' must use LOCAL midnight, not UTC midnight.
    In BST (UTC+1), local midnight is 23:00 UTC the night before.

    Args:
        tz_name: IANA timezone string, e.g. "Europe/London".
        now: Optional datetime for testing; defaults to current wall-clock time.

    Returns:
        UTC epoch seconds of today's local midnight.
    """
    tz = zoneinfo.ZoneInfo(tz_name)
    if now is None:
        now = datetime.datetime.now(tz)
    else:
        now = now.astimezone(tz)
    today_local = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(today_local.astimezone(datetime.UTC).timestamp())


# ---------------------------------------------------------------------------
# Today-so-far query helper
# ---------------------------------------------------------------------------


def today_so_far(
    conn: sqlite3.Connection,
    midnight_ts: int,
    node_id: str,
) -> dict[str, Any]:
    """Query today's weather summary stats since local midnight.

    Runs the Pattern 8 SQL from RESEARCH.md against an open connection.
    Dewpoint high/low are derived from the temp+humidity extremes.

    Returns:
        dict with keys: high_c, low_c, pressure_high_hpa, pressure_low_hpa,
        peak_lux, dewpoint_high_c, dewpoint_low_c, since_ts.
        All values are None when no rows exist since midnight.
    """
    cursor = conn.execute(
        """
        SELECT
            MAX(temp_c)        AS high_c,
            MIN(temp_c)        AS low_c,
            MAX(pressure_hpa)  AS pressure_high_hpa,
            MIN(pressure_hpa)  AS pressure_low_hpa,
            MAX(lux)           AS peak_lux,
            MIN(ts)            AS since_ts,
            MAX(humidity_pct)  AS humidity_high,
            MIN(humidity_pct)  AS humidity_low
        FROM weather
        WHERE ts >= ?
          AND node_id = ?
        """,
        (midnight_ts, node_id),
    )
    row = cursor.fetchone()

    if row is None or row["high_c"] is None:
        return {
            "high_c": None,
            "low_c": None,
            "pressure_high_hpa": None,
            "pressure_low_hpa": None,
            "peak_lux": None,
            "dewpoint_high_c": None,
            "dewpoint_low_c": None,
            "since_ts": None,
        }

    # Dewpoint high from high temp + high humidity; low from low temp + low humidity.
    dewpoint_high: float | None = None
    dewpoint_low: float | None = None
    if row["high_c"] is not None and row["humidity_high"] is not None:
        dewpoint_high = round(dewpoint_c(row["high_c"], row["humidity_high"]), 1)
    if row["low_c"] is not None and row["humidity_low"] is not None:
        dewpoint_low = round(dewpoint_c(row["low_c"], row["humidity_low"]), 1)

    return {
        "high_c": round(row["high_c"], 1) if row["high_c"] is not None else None,
        "low_c": round(row["low_c"], 1) if row["low_c"] is not None else None,
        "pressure_high_hpa": (
            round(row["pressure_high_hpa"], 1) if row["pressure_high_hpa"] is not None else None
        ),
        "pressure_low_hpa": (
            round(row["pressure_low_hpa"], 1) if row["pressure_low_hpa"] is not None else None
        ),
        "peak_lux": round(row["peak_lux"], 1) if row["peak_lux"] is not None else None,
        "dewpoint_high_c": dewpoint_high,
        "dewpoint_low_c": dewpoint_low,
        "since_ts": row["since_ts"],
    }
