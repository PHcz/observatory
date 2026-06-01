"""STP (standard temperature & pressure) correction for muon flux.

Mirrors the canonical UKRAA_PicoMuon method (scripts/PlotData90DaysSTPACM0.gp):

    corrected = raw / ( ((T_degC + 273.15) / 293.15) * (1013.25 / P_hPa) )

i.e. the rate is normalized to standard conditions (20 degC, 1013.25 hPa) using
the ideal-gas density ratio. Atmospheric pressure attenuates muon flux, so this
removes the barometric (and first-order temperature) variation from the rate.

Returns the raw rate unchanged when temperature or pressure is missing/invalid
(can't correct without both) — never raises, never produces NaN/inf.
"""

from __future__ import annotations

REFERENCE_TEMP_K: float = 293.15  # 20 degC
REFERENCE_PRESSURE_HPA: float = 1013.25


def stp_factor(temp_c: float, pressure_hpa: float) -> float:
    """The STP density ratio; divide a raw rate by this to normalize it."""
    return ((temp_c + 273.15) / REFERENCE_TEMP_K) * (REFERENCE_PRESSURE_HPA / pressure_hpa)


def stp_corrected_rate(
    rate: float | None,
    temp_c: float | None,
    pressure_hpa: float | None,
) -> float | None:
    """Pressure-correct a muon rate. Unchanged if rate/temp/pressure invalid."""
    if rate is None:
        return None
    if temp_c is None or pressure_hpa is None or pressure_hpa <= 0:
        return rate
    factor = stp_factor(temp_c, pressure_hpa)
    if factor <= 0:
        return rate
    return rate / factor
