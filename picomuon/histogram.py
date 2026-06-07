"""ADC histogram for coincidence events (Landau-ish MIP peak).

Wave 0 stub: locked signatures only. Logic lands in Wave 2.
"""

from __future__ import annotations

import polars as pl


def adc_histogram(df: pl.DataFrame, id: str = "C", bin_width: int = 20) -> pl.DataFrame:
    """Bin ADC values 0-1023 in steps of bin_width. Returns bin_center, count."""
    raise NotImplementedError


def plot_histogram(hist: pl.DataFrame, ax=None):  # type: ignore[no-untyped-def]
    """Plot the ADC histogram, highlighting the modal bin. Returns a matplotlib Figure."""
    raise NotImplementedError
