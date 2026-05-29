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
