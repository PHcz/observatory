"""Normalized earthquake event shape shared across USGS / EMSC / BGS parsers."""

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
