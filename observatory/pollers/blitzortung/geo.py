"""Haversine great-circle distance — pure stdlib, < 0.5% error at <500km.

Used by ``BlitzortungClient`` to drop strikes outside
``settings.poller_lightning_radius_km`` before insert. The full Vincenty
formula is overkill for the lightning radius (haversine error at 500 km is
under 0.2 km).
"""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two (lat, lon) pairs, in kilometres."""
    rlat1, rlat2 = radians(lat1), radians(lat2)
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(rlat1) * cos(rlat2) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))
