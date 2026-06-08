"""Phase 16 ENH-01 — absolute muon flux computation.

Converts wall-clock rate (events/min) to absolute flux (cm^-2 min^-1) using
the detector's effective area. The result is RAW — not dead-time corrected.

Dead-time honesty line: this function divides by area only. No dead-time
correction is applied because the live path (muon_events in SQLite) does not
carry the elapsed/dead-time fields the PicoMuon CSV does. The offline CLI
(picomuon.rates.flux) remains the dead-time-corrected source of truth.

The aT effective-temperature correction is DEFERRED (Phase 16 CONTEXT.md, Open
questions). Do NOT add temperature-regression code here.
"""

from __future__ import annotations

from picomuon.rates import AREA_CM2

# Canonical sea-level muon flux benchmark: ~1 cm^-2 min^-1 at sea level for a
# horizontal detector with AREA_CM2 = 25 cm^2, used as a reference baseline on
# the frontend gain-drift chart.
SEA_LEVEL_FLUX_CM2_MIN: float = 1.0


def absolute_flux(rate_per_min: float, area_cm2: float = AREA_CM2) -> float:
    """Wall-clock absolute flux cm^-2 min^-1. RAW — not dead-time corrected.

    Args:
        rate_per_min: events per minute (wall-clock, bucketed count * 60 / bucket_sec).
        area_cm2: detector effective area in cm^2 (default: PicoMuon AREA_CM2 = 25.0).

    Returns:
        Flux in cm^-2 min^-1.
    """
    return rate_per_min / area_cm2
