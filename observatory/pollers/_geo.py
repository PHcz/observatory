"""Great-circle distance helper (Phase 8.5 UI-18).

Stdlib-only haversine. Pattern matches the haversine already used in
observatory/pollers/blitzortung/; deliberately not extracted from there in
this phase to avoid touching the Phase 5 lightning poller. Future cleanup
can collapse the two implementations.
"""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres between two WGS-84 points.

    Sub-km accurate at 250 km radius (acceptable for UI-18 threshold).
    Symmetric in argument order.
    """
    rlat1, rlat2 = radians(lat1), radians(lat2)
    dlat = rlat2 - rlat1
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(rlat1) * cos(rlat2) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))
