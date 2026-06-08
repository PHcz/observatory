"""Phase 16 ENH-05: weather derived metrics — MSLP, Zambretti, heat index, dewpoint.

RED: imports from observatory.weather.derived which does not exist yet.
This test gates Wave 1 implementation.
"""

from __future__ import annotations

import pytest

from observatory.weather.derived import (
    ZAMBRETTI_FORECAST,
    dewpoint_c,
    heat_index_c,
    station_to_mslp,
    zambretti_z,
)


def test_mslp_zero_alt() -> None:
    """At sea level (altitude=0), MSLP ≈ station pressure."""
    result = station_to_mslp(1013.25, 0.0, 15.0)
    assert result == pytest.approx(1013.25, abs=0.01)


def test_mslp_50m() -> None:
    """At 50m altitude, MSLP should be ~6 hPa higher than station pressure."""
    result = station_to_mslp(1007.0, 50.0, 15.0)
    assert result == pytest.approx(1013.1, abs=0.5)


def test_mslp_increases_with_altitude() -> None:
    """MSLP must be >= station pressure for positive altitude."""
    assert station_to_mslp(1000.0, 100.0, 15.0) > 1000.0


def test_zambretti_steady() -> None:
    """Zambretti with steady tendency at 1013 hPa → Z in [1..26] and in ZAMBRETTI_FORECAST."""
    z = zambretti_z(1013.0, "steady")
    expected_z = max(1, min(26, round(147 - 0.13 * 1013.0)))
    assert z == expected_z
    assert z in ZAMBRETTI_FORECAST


def test_zambretti_falling() -> None:
    """Zambretti with falling tendency → lower Z values (more unsettled)."""
    z = zambretti_z(1000.0, "falling")
    assert 1 <= z <= 26
    assert z in ZAMBRETTI_FORECAST


def test_zambretti_rising() -> None:
    """Zambretti with rising tendency → higher Z values (more settled)."""
    z = zambretti_z(1020.0, "rising")
    assert 1 <= z <= 26
    assert z in ZAMBRETTI_FORECAST


def test_zambretti_clamped_min() -> None:
    """Z is always >= 1 (even with extreme pressure)."""
    z = zambretti_z(2000.0, "rising")  # very high pressure → big Z → clamped to 26
    assert 1 <= z <= 26


def test_zambretti_clamped_max() -> None:
    """Z is always <= 26 (even with very low pressure)."""
    z = zambretti_z(500.0, "falling")
    assert 1 <= z <= 26


def test_zambretti_forecast_has_26_entries() -> None:
    """ZAMBRETTI_FORECAST must have exactly 26 entries (1..26)."""
    assert len(ZAMBRETTI_FORECAST) == 26
    assert set(ZAMBRETTI_FORECAST.keys()) == set(range(1, 27))


def test_heat_index_below_threshold() -> None:
    """Below 26.7°C heat index is not in heat-stress regime; returns temp unchanged."""
    assert heat_index_c(20.0, 60.0) == 20.0


def test_heat_index_cold() -> None:
    """At 10°C, feels-like = station temp."""
    assert heat_index_c(10.0, 80.0) == 10.0


def test_heat_index_above_threshold() -> None:
    """Above 26.7°C with high humidity, feels-like > actual temp."""
    result = heat_index_c(35.0, 80.0)
    assert result > 35.0


def test_dewpoint_saturated() -> None:
    """At 100% humidity, dewpoint ≈ air temperature."""
    result = dewpoint_c(10.0, 100.0)
    assert result == pytest.approx(10.0, abs=0.1)


def test_dewpoint_dry() -> None:
    """At low humidity, dewpoint is well below air temperature."""
    result = dewpoint_c(20.0, 30.0)
    assert result < 10.0
