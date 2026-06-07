"""Dead-time-corrected muon rates and flux.

Wave 0 stub: locked signatures only. Logic lands in Wave 1.
"""

from __future__ import annotations

import polars as pl

#: PicoMuon scintillator active area, cm2 (50 x 50 mm).
AREA_CM2 = 25.0


def bin_rate(df: pl.DataFrame, id: str = "C", bucket: str = "10m") -> pl.DataFrame:
    """Bin events into time buckets with dead-time-corrected rate_hz.

    Returns columns bucket_start, count, elapsed_s, dead_s, live_s,
    rate_hz, pressure_mean, temperature_mean. live_s = elapsed_s - dead_s
    is the rate denominator (not wall-clock).
    """
    raise NotImplementedError


def flux(df: pl.DataFrame, id: str = "C") -> float:
    """Muons per cm² per minute over AREA_CM2, dead-time corrected."""
    raise NotImplementedError
