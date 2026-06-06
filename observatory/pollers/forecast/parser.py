"""Column-zip parser for the Open-Meteo forecast response (Phase 10, FCAST-01).

Open-Meteo returns COLUMN-ORIENTED JSON: parallel arrays under ``hourly``/``daily``
(``hourly.time[i]`` lines up with ``hourly.temperature_2m[i]`` ...), NOT a list of
row objects like the earthquake/space-weather pollers. So this parser zips the
columns into per-hour / per-day rows.

Timestamp carve-out: ``hourly.time[i]`` is naive local wall-clock ISO without an
offset (e.g. ``2026-06-06T00:00``); ``daily.time[i]`` is a bare ``YYYY-MM-DD``
local date. To store the project-standard UTC epoch we parse the naive string as
if UTC then subtract ``utc_offset_seconds``. These strings are deliberately NOT
routed through the strict shared ISO timestamp helper in ``observatory.pollers``
— they carry no offset, exactly like the NOAA naive-UTC and BGS pubDate
carve-outs (STATE 05-03 / 04-04).

Parser-strict contract: any structural problem (missing key, ragged arrays, bad
JSON) raises ``ValueError`` so the oneshot ``__main__`` can catch a single
exception type and write a ``parse_fail`` audit row.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime

from observatory.pollers._types import ForecastDaily, ForecastHourly

_HOURLY_KEYS = (
    "temperature_2m",
    "apparent_temperature",
    "relative_humidity_2m",
    "surface_pressure",
    "precipitation_probability",
    "weather_code",
    "wind_speed_10m",
)
_DAILY_KEYS = (
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_probability_max",
    "weather_code",
    "wind_speed_10m_max",
)


def _local_naive_to_utc_epoch(iso: str, offset_seconds: int) -> int:
    """Naive-local wall-clock ISO -> UTC epoch, via the utc_offset carve-out."""
    return int(datetime.fromisoformat(iso).replace(tzinfo=UTC).timestamp()) - offset_seconds


def parse_forecast(
    body: bytes,
) -> tuple[list[ForecastHourly], list[ForecastDaily], dict[str, int | str]]:
    """Parse an Open-Meteo forecast response into hourly + daily rows + meta.

    Returns ``(hourly, daily, meta)`` where ``meta`` carries
    ``utc_offset_seconds`` (int), ``timezone`` (str) and ``fetched_at`` (int).
    Raises ``ValueError`` on any missing key, ragged array, or bad JSON.
    """
    try:
        data = json.loads(body)
        off = int(data["utc_offset_seconds"])

        h = data["hourly"]
        htimes = h["time"]
        n_h = len(htimes)
        for key in _HOURLY_KEYS:
            if len(h[key]) != n_h:
                raise ValueError(f"ragged hourly arrays: {key}")
        hourly = [
            ForecastHourly(
                ts=_local_naive_to_utc_epoch(htimes[i], off),
                temp_c=h["temperature_2m"][i],
                apparent_temp_c=h["apparent_temperature"][i],
                relative_humidity_pct=h["relative_humidity_2m"][i],
                surface_pressure_hpa=h["surface_pressure"][i],
                precip_prob_pct=h["precipitation_probability"][i],
                weather_code=h["weather_code"][i],
                wind_speed_kmh=h["wind_speed_10m"][i],
            )
            for i in range(n_h)
        ]

        d = data["daily"]
        dtimes = d["time"]
        n_d = len(dtimes)
        for key in _DAILY_KEYS:
            if len(d[key]) != n_d:
                raise ValueError(f"ragged daily arrays: {key}")
        daily = [
            ForecastDaily(
                ts=_local_naive_to_utc_epoch(dtimes[i], off),
                temp_max_c=d["temperature_2m_max"][i],
                temp_min_c=d["temperature_2m_min"][i],
                precip_prob_max_pct=d["precipitation_probability_max"][i],
                weather_code=d["weather_code"][i],
                wind_speed_max_kmh=d["wind_speed_10m_max"][i],
            )
            for i in range(n_d)
        ]

        meta: dict[str, int | str] = {
            "utc_offset_seconds": off,
            "timezone": str(data["timezone"]),
            "fetched_at": int(time.time()),
        }
    except (KeyError, TypeError, IndexError, json.JSONDecodeError) as exc:
        raise ValueError(f"malformed Open-Meteo forecast response: {exc}") from exc

    return hourly, daily, meta
