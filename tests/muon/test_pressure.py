"""Tests for STP pressure correction (UKRAA method)."""

from __future__ import annotations

import math

from observatory.muon.pressure import (
    REFERENCE_PRESSURE_HPA,
    stp_corrected_rate,
    stp_factor,
)


def test_no_correction_at_reference_conditions() -> None:
    # 20 degC + 1013.25 hPa → factor 1.0 → rate unchanged.
    assert math.isclose(stp_factor(20.0, REFERENCE_PRESSURE_HPA), 1.0, rel_tol=1e-9)
    assert math.isclose(
        stp_corrected_rate(100.0, 20.0, REFERENCE_PRESSURE_HPA), 100.0, rel_tol=1e-9
    )


def test_low_pressure_scales_rate_down() -> None:
    # Lower pressure lets more muons through (raw higher); correction divides by a
    # factor < 1 → corrected rate is HIGHER than raw? No: factor = (T)*(1013.25/P);
    # at low P, 1013.25/P > 1 → factor > 1 → corrected < raw. Verify direction.
    corrected = stp_corrected_rate(100.0, 20.0, 990.0)
    factor = stp_factor(20.0, 990.0)
    assert factor > 1.0
    assert corrected is not None and corrected < 100.0
    assert math.isclose(corrected, 100.0 / factor, rel_tol=1e-9)


def test_high_pressure_scales_rate_up() -> None:
    corrected = stp_corrected_rate(100.0, 20.0, 1030.0)
    factor = stp_factor(20.0, 1030.0)
    assert factor < 1.0
    assert corrected is not None and corrected > 100.0


def test_missing_temp_returns_raw() -> None:
    assert stp_corrected_rate(100.0, None, 1013.25) == 100.0


def test_missing_pressure_returns_raw() -> None:
    assert stp_corrected_rate(100.0, 20.0, None) == 100.0


def test_nonpositive_pressure_returns_raw() -> None:
    assert stp_corrected_rate(100.0, 20.0, 0.0) == 100.0
    assert stp_corrected_rate(100.0, 20.0, -5.0) == 100.0


def test_none_rate_returns_none() -> None:
    assert stp_corrected_rate(None, 20.0, 1013.25) is None
