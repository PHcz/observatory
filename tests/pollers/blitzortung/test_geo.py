"""Haversine great-circle distance tests."""

from __future__ import annotations

import pytest


def test_zero_distance() -> None:
    from observatory.pollers.blitzortung.geo import haversine_km

    assert haversine_km(51.5, -0.1, 51.5, -0.1) == pytest.approx(0.0, abs=1e-6)


def test_london_to_paris() -> None:
    from observatory.pollers.blitzortung.geo import haversine_km

    # London (51.5074, -0.1278) → Paris (48.8566, 2.3522) ≈ 343 km
    d = haversine_km(51.5074, -0.1278, 48.8566, 2.3522)
    assert d == pytest.approx(343.0, abs=5.0)


def test_antipodal_quarter_world() -> None:
    from observatory.pollers.blitzortung.geo import haversine_km

    # (0,0) → (0,180) is half-way around the equator ≈ 20015 km
    d = haversine_km(0.0, 0.0, 0.0, 180.0)
    assert d == pytest.approx(20015.0, abs=5.0)


@pytest.mark.parametrize(
    "lat1,lon1,lat2,lon2",
    [
        (51.5, -0.1, 48.8, 2.3),
        (0.0, 0.0, 45.0, 90.0),
        (-33.9, 151.2, 35.7, 139.7),  # Sydney → Tokyo
    ],
)
def test_symmetry(lat1: float, lon1: float, lat2: float, lon2: float) -> None:
    from observatory.pollers.blitzortung.geo import haversine_km

    forward = haversine_km(lat1, lon1, lat2, lon2)
    backward = haversine_km(lat2, lon2, lat1, lon1)
    assert forward == pytest.approx(backward, rel=1e-9)


def test_within_500km_radius() -> None:
    """London → Paris (≈343 km) is inside a 500 km radius."""
    from observatory.pollers.blitzortung.geo import haversine_km

    assert haversine_km(51.5074, -0.1278, 48.8566, 2.3522) < 500.0


def test_outside_500km_radius() -> None:
    """London → New York (≈5570 km) is outside any reasonable lightning radius."""
    from observatory.pollers.blitzortung.geo import haversine_km

    assert haversine_km(51.5074, -0.1278, 40.7128, -74.0060) > 500.0
