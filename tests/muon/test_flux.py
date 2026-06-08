"""Phase 16 ENH-01: absolute flux computation.

RED: imports from observatory.muon.flux which does not exist yet.
This test gates Wave 1 implementation.

Tests:
- absolute_flux(75.0, 25.0) == 3.0
- SEA_LEVEL_FLUX_CM2_MIN == 1.0
"""

from __future__ import annotations

from observatory.muon.flux import SEA_LEVEL_FLUX_CM2_MIN, absolute_flux


def test_absolute_flux() -> None:
    """75 events/min over 25 cm^2 = 3.0 cm^-2 min^-1."""
    assert absolute_flux(75.0, 25.0) == 3.0


def test_absolute_flux_default_area() -> None:
    """Default area is 25.0 cm^2 (canonical PicoMuon value)."""
    assert absolute_flux(25.0) == 1.0


def test_sea_level_flux_constant() -> None:
    """Sea-level reference flux is the textbook 1.0 cm^-2 min^-1."""
    assert SEA_LEVEL_FLUX_CM2_MIN == 1.0
