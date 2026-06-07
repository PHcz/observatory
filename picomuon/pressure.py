"""Barometric coefficient fit: ln(rate) = a + beta * (P - P_mean).

Fits the cosmic-ray barometric coefficient by linear regression of the
log coincidence rate against pressure (centred on the mean). The slope is the
fractional rate change per hPa; multiplied by 100 it is the conventional
barometric coefficient in %/hPa (expected ~ -0.15 to -0.20 for muons).

Limitation (MU2-02): the PicoMuon's internal BMP280 also reports a
*temperature*, but that sensor sits inside the warm detector case and tracks
the enclosure, NOT the atmosphere. It is therefore the wrong variable for a
temperature-coefficient fit, so v1 fits the barometric (pressure) coefficient
only. The warm-case bias also makes the absolute pressure reading slightly
high; this is not corrected in v1 (documented in the README).
"""

from __future__ import annotations

from dataclasses import dataclass

import matplotlib

matplotlib.use("Agg")  # headless backend — no DISPLAY on the Pi / CI

import matplotlib.pyplot as plt
import numpy as np
import polars as pl
from matplotlib.figure import Figure
from scipy import stats
from scipy.stats import t as student_t

# Hyborg sage accent (frontend/src/lib/styles/tokens.css --accent).
_ACCENT = "#6b8e6b"


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
    """Fit ln(rate) vs (P - P_mean) by linear regression, returning BarometricFit.

    Buckets with a null or non-positive ``rate_hz`` are filtered BEFORE the log
    (Pitfall 2 — ``ln(0)`` poisons the regression with -inf/NaN). The slope is
    the fractional rate change per hPa; ``beta`` is that slope x 100 (%/hPa).
    """
    d = binned_df.filter(pl.col("rate_hz").is_not_null() & (pl.col("rate_hz") > 0))
    p = d["pressure_mean"].to_numpy()
    y = np.log(d["rate_hz"].to_numpy())
    p_mean = float(p.mean())
    x = p - p_mean
    res = stats.linregress(x, y)
    beta_pct_per_hpa = float(res.slope) * 100.0  # ln-rate fractional slope -> %/hPa
    r_squared = float(res.rvalue) ** 2
    return BarometricFit(
        beta=beta_pct_per_hpa,
        r_squared=r_squared,
        p_value=float(res.pvalue),
        slope=float(res.slope),
        intercept=float(res.intercept),
        p_mean=p_mean,
        slope_stderr=float(res.stderr),
        n=len(x),
    )


def plot_fit(fit: BarometricFit, binned_df: pl.DataFrame, ax=None) -> Figure:  # type: ignore[no-untyped-def]
    """Plot ln(rate) vs pressure with the regression line + 95% CI band.

    The band is a slope-uncertainty band: at each pressure the half-width is
    ``tcrit * slope_stderr * |P - P_mean|`` (it pinches to zero at the pivot
    P_mean and widens with the lever arm). This is honest about where the slope
    is best constrained and is the publishable-out-of-box choice per RESEARCH
    Open Q3 (a full prediction band is acceptable but not required).
    """
    d = binned_df.filter(pl.col("rate_hz").is_not_null() & (pl.col("rate_hz") > 0))
    p = d["pressure_mean"].to_numpy()
    y = np.log(d["rate_hz"].to_numpy())

    if ax is None:
        fig, ax = plt.subplots(figsize=(7, 4.5))
    else:
        fig = ax.figure

    ax.scatter(p, y, s=18, color=_ACCENT, alpha=0.7, label="binned data", zorder=3)

    # Fitted line over a pressure grid (x is centred on p_mean).
    p_grid = np.linspace(float(p.min()), float(p.max()), 200)
    x_grid = p_grid - fit.p_mean
    y_line = fit.intercept + fit.slope * x_grid
    ax.plot(p_grid, y_line, color="#111111", lw=1.5, label="fit", zorder=4)

    # 95% CI band (Student-t critical value for the slope; n-2 dof).
    tcrit = float(student_t.ppf(0.975, df=max(fit.n - 2, 1)))
    half_width = tcrit * fit.slope_stderr * np.abs(x_grid)
    ax.fill_between(
        p_grid,
        y_line - half_width,
        y_line + half_width,
        color=_ACCENT,
        alpha=0.18,
        lw=0,
        label="95% CI",
        zorder=2,
    )

    ax.set_xlabel("Pressure (hPa)")
    ax.set_ylabel("ln(rate / Hz)")
    ax.set_title(f"β = {fit.beta:.3f} %/hPa  ·  R² = {fit.r_squared:.2f}")
    ax.legend(frameon=False, fontsize=9)
    fig.tight_layout()
    return fig
