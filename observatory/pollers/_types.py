"""Normalized event shapes shared across pollers (Phase 4 earthquakes + Phase 5)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EarthquakeEvent:
    """One earthquake, normalized across upstream sources.

    Source-specific parsers absorb upstream naming differences; the write
    layer and downstream API consumers only see this shape.

    ``is_local`` (Phase 8.5 UI-18) is True iff the event is from BGS
    (UK-only source) OR within ``settings.observatory_local_radius_km``
    of ``HOME_LAT``/``HOME_LON``. Computed in each poller's __main__
    after parsing and before writing; default False keeps parser sites
    backward-compatible (parsers don't set it).
    """

    source: str  # 'usgs' | 'emsc' | 'bgs'
    external_id: str  # USGS feature.id | EMSC props.unid | BGS link-derived 14-digit
    ts: int  # UTC unix epoch seconds
    magnitude: float
    depth_km: float | None
    latitude: float
    longitude: float
    place: str | None
    is_local: bool = False  # UI-18 — BGS OR <= OBSERVATORY_LOCAL_RADIUS_KM from HOME_LAT/HOME_LON


@dataclass(frozen=True, slots=True)
class SpaceWeatherSnapshot:
    """One NOAA SWPC poll's worth of space-weather state (POLL-04).

    ``ts`` is the poll's ``started_at`` (NOT the individual upstream
    field timestamps — those vary per endpoint). Any of ``kp_index``,
    ``solar_wind_kms``, ``flare_class``, ``flare_peak_ts`` may be
    ``None`` when its source endpoint failed (partial-fetch tolerance —
    the row is still written with NULLs and ``poller_runs.status='partial'``).
    """

    ts: int  # poll started_at (unix epoch seconds)
    kp_index: float | None
    solar_wind_kms: float | None
    flare_class: str | None  # NOAA scale, e.g. "C4.6"
    flare_peak_ts: int | None  # UTC epoch of the flare peak


@dataclass(frozen=True, slots=True)
class AuroraSnapshot:
    """One AuroraWatch UK status snapshot (POLL-06).

    No dedup at the writer level — state-machine transitions are operationally
    meaningful (a green->amber transition that we skipped via dedup would be
    a regression in the dashboard story).
    """

    ts: int  # UTC unix epoch seconds (from <updated><datetime>)
    status: str  # 'green' | 'yellow' | 'amber' | 'red' (lowercased)
    detail: str | None  # colon-joined project_id:site_id, or None when both empty


@dataclass(frozen=True, slots=True)
class LightningStrike:
    """One Blitzortung lightning strike inside the configured radius (POLL-05).

    ``distance_km`` is pre-computed by the poller (haversine vs ``settings.home_lat``
    / ``home_lon``) so the dashboard query is a trivial column scan rather than
    a per-row recomputation. Strikes outside ``settings.poller_lightning_radius_km``
    are dropped before construction; this dataclass only carries strikes that
    will be written.
    """

    ts: int  # UTC unix epoch seconds (Blitzortung emits ns; poller divides)
    latitude: float
    longitude: float
    distance_km: float


@dataclass(frozen=True, slots=True)
class ForecastHourly:
    """One forecast hour from Open-Meteo (Phase 10, FCAST-01/02).

    ``ts`` is a UTC epoch computed as the naive-local wall-clock time MINUS
    ``utc_offset_seconds`` from the response. This is a documented carve-out
    from the strict shared ``parse_ts`` helper: Open-Meteo ``time`` strings
    carry no offset (e.g. ``2026-06-06T00:00``), exactly like the NOAA naive-UTC
    and BGS pubDate carve-outs (STATE 05-03 / 04-04).

    ``relative_humidity_pct`` + ``surface_pressure_hpa`` are carried (beyond the
    CONTEXT panel-strip variable list) to honour the locked forecast-vs-actual
    temp+humidity+pressure decision (10-RESEARCH Open Question 1). Every field is
    nullable: Open-Meteo can emit ``null`` array elements (Pitfall 6).
    """

    ts: int  # UTC epoch (naive-local wall-clock - utc_offset_seconds)
    temp_c: float | None
    apparent_temp_c: float | None
    relative_humidity_pct: int | None
    surface_pressure_hpa: float | None
    precip_prob_pct: int | None
    weather_code: int | None
    wind_speed_kmh: float | None


@dataclass(frozen=True, slots=True)
class ForecastDaily:
    """One forecast day from Open-Meteo (Phase 10, FCAST-01/02).

    ``ts`` is the UTC epoch of the LOCAL-day start: Open-Meteo ``daily.time[i]``
    is a bare ``YYYY-MM-DD`` local date parsed to local midnight, then shifted by
    ``-utc_offset_seconds`` (same naive-local→UTC carve-out as ForecastHourly).
    All fields nullable (Pitfall 6).
    """

    ts: int  # UTC epoch of local-day start
    temp_max_c: float | None
    temp_min_c: float | None
    precip_prob_max_pct: int | None
    weather_code: int | None
    wind_speed_max_kmh: float | None


@dataclass(frozen=True, slots=True)
class AirQualitySnapshot:
    """One current air-quality reading from Open-Meteo (Phase 11, OAQ-01).

    ``ts`` is a UTC epoch computed as the naive-local wall-clock ``current.time``
    MINUS ``utc_offset_seconds`` from the response — the same documented carve-out
    from the strict shared ``parse_ts`` helper used by ForecastHourly/Daily, the
    NOAA naive-UTC and BGS pubDate carve-outs (STATE 05-03 / 04-04).

    Every measurement field is nullable: Open-Meteo can emit ``null`` for any
    variable (e.g. pollen out of season, sensor gaps). The cache holds exactly one
    such snapshot (migration 0006 ``air_quality`` id=1, replace-on-fetch).
    """

    ts: int  # UTC epoch (naive-local current.time - utc_offset_seconds)
    european_aqi: float | None
    pm2_5: float | None
    pm10: float | None
    nitrogen_dioxide: float | None
    ozone: float | None
    sulphur_dioxide: float | None
    uv_index: float | None
    alder_pollen: float | None
    birch_pollen: float | None
    grass_pollen: float | None
    mugwort_pollen: float | None
    olive_pollen: float | None
    ragweed_pollen: float | None
