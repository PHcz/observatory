"""Barometric coefficient fit: ln(rate) = a + beta * (P - P_mean).

Wave 0 stub: locked signatures only. Logic lands in Wave 2.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl


@dataclass(frozen=True, slots=True)
class BarometricFit:
    """Result of the barometric regression."""

    beta: float
    r_squared: float
    p_value: float
    slope: float
    intercept: float
    p_mean: float
    slope_stderr: float
    n: int


def barometric_fit(binned_df: pl.DataFrame) -> BarometricFit:
    """Fit ln(rate) vs (P - P_mean) by linear regression, returning BarometricFit."""
    raise NotImplementedError


def plot_fit(fit: BarometricFit, binned_df: pl.DataFrame, ax=None):  # type: ignore[no-untyped-def]
    """Plot rate vs pressure with the regression line. Returns a matplotlib Figure."""
    raise NotImplementedError
