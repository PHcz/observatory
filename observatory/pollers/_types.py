"""Normalized event shapes shared across pollers (Phase 4 earthquakes + Phase 5 aurora)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EarthquakeEvent:
    """One earthquake, normalized across upstream sources.

    Source-specific parsers absorb upstream naming differences; the write
    layer and downstream API consumers only see this shape.
    """

    source: str  # 'usgs' | 'emsc' | 'bgs'
    external_id: str  # USGS feature.id | EMSC props.unid | BGS link-derived 14-digit
    ts: int  # UTC unix epoch seconds
    magnitude: float
    depth_km: float | None
    latitude: float
    longitude: float
    place: str | None


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
