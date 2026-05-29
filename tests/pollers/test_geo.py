"""Phase 8.5 UI-18: haversine_km great-circle distance helper.

Tests verify stdlib-only haversine against well-known reference distances:
London is the origin; Paris/Edinburgh/Dublin/Brussels are the targets. Each
threshold is tight enough to catch a wrong-Earth-radius bug or a unit slip
(km vs metres) while still tolerating the ~0.5% inherent haversine drift.
"""

from __future__ import annotations

import pytest


def test_zero_distance() -> None:
    from observatory.pollers._geo import haversine_km

    assert haversine_km(0.0, 0.0, 0.0, 0.0) == 0.0


def test_london_to_paris() -> None:
    """London (51.5074, -0.1278) -> Paris (48.8566, 2.3522) ~ 343.5 km."""
    from observatory.pollers._geo import haversine_km

    d = haversine_km(51.5074, -0.1278, 48.8566, 2.3522)
    assert 342.5 < d < 344.5, f"expected ~343.5, got {d}"


def test_london_to_edinburgh() -> None:
    """London -> Edinburgh (55.9533, -3.1883) ~ 534 km."""
    from observatory.pollers._geo import haversine_km

    d = haversine_km(51.5074, -0.1278, 55.9533, -3.1883)
    assert 533.0 < d < 535.0, f"expected ~534, got {d}"


def test_london_to_dublin_outside_250km() -> None:
    """London -> Dublin (53.3498, -6.2603) ~ 463 km — outside 250 km radius."""
    from observatory.pollers._geo import haversine_km

    d = haversine_km(51.5074, -0.1278, 53.3498, -6.2603)
    assert 462.0 < d < 464.0, f"expected ~463, got {d}"
    # And critically: > 250 (Dublin must NOT be flagged is_local from London centre)
    assert d > 250.0


def test_london_to_brussels() -> None:
    """London -> Brussels (50.8503, 4.3517) ~ 320 km."""
    from observatory.pollers._geo import haversine_km

    d = haversine_km(51.5074, -0.1278, 50.8503, 4.3517)
    assert 319.0 < d < 321.0, f"expected ~320, got {d}"


def test_haversine_is_symmetric() -> None:
    from observatory.pollers._geo import haversine_km

    forward = haversine_km(51.5074, -0.1278, 48.8566, 2.3522)
    reverse = haversine_km(48.8566, 2.3522, 51.5074, -0.1278)
    assert forward == pytest.approx(reverse, abs=0.001)


def test_earth_radius_constant() -> None:
    from observatory.pollers._geo import EARTH_RADIUS_KM

    assert EARTH_RADIUS_KM == 6371.0088
