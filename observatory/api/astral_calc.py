"""Phase 6 — astronomical calculations via astral 3.x. Implemented by Plan 06-01."""

from __future__ import annotations

import logging
import math
from datetime import UTC, date
from typing import Any

from astral import LocationInfo
from astral import moon as astral_moon
from astral.sun import sun

logger = logging.getLogger(__name__)

_SYNODIC_MONTH_DAYS: float = 29.53


def compute_moon_illumination(phase_days: float) -> float:
    """Return moon illumination percentage (0.0-100.0) from days-since-new-moon.

    Uses the cosine formula: (1 - cos(2π * phase_days / 29.53)) / 2 * 100

    Args:
        phase_days: Days elapsed since the last new moon (0.0 to ~29.53).

    Returns:
        Illumination percentage rounded to 1 decimal place.
    """
    raw = (1 - math.cos(2 * math.pi * phase_days / _SYNODIC_MONTH_DAYS)) / 2 * 100
    return round(raw, 1)


def get_astronomy(
    lat: float,
    lon: float,
    today: date | None = None,
) -> dict[str, Any]:
    """Return sunrise/sunset timestamps + moon phase data for the given location and date.

    Args:
        lat: Latitude in decimal degrees.
        lon: Longitude in decimal degrees.
        today: Date to calculate for. Defaults to today (UTC). Injection point for tests.

    Returns:
        Dict with keys:
            sunrise_ts (int): UTC epoch seconds.
            sunset_ts (int): UTC epoch seconds.
            moon_phase (float): Normalised phase in [0.0, 1.0).
                0.0 = new moon, 0.5 = full moon.
            moon_illumination_pct (float): Illumination percentage in [0.0, 100.0].
    """
    if today is None:
        from datetime import datetime

        today = datetime.now(tz=UTC).date()

    loc = LocationInfo(latitude=lat, longitude=lon, timezone="UTC")

    # --- Sunrise / Sunset ---
    sunrise_ts: int = 0
    sunset_ts: int = 0
    try:
        s = sun(loc.observer, date=today)
        sunrise_ts = int(s["sunrise"].timestamp())
        sunset_ts = int(s["sunset"].timestamp())
    except ValueError:
        # astral 3.x raises ValueError for polar night / midnight sun extremes
        logger.warning(
            "astral ValueError for lat=%s lon=%s date=%s (polar night/midnight sun?)",
            lat,
            lon,
            today,
        )
    except Exception:
        logger.warning(
            "Unexpected error computing sun times for lat=%s lon=%s date=%s",
            lat,
            lon,
            today,
            exc_info=True,
        )

    # --- Moon phase ---
    phase_days = astral_moon.phase(today)
    # Clamp to [0, 29.53) defensively (astral should always be in range)
    phase_days = phase_days % _SYNODIC_MONTH_DAYS
    moon_phase = round(phase_days / _SYNODIC_MONTH_DAYS, 4)

    illumination = compute_moon_illumination(phase_days)

    return {
        "sunrise_ts": sunrise_ts,
        "sunset_ts": sunset_ts,
        "moon_phase": moon_phase,
        "moon_illumination_pct": illumination,
    }
