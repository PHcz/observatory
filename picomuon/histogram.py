"""ADC histogram for coincidence events (Landau-ish MIP peak).

Bins the uncalibrated ADC pulse amplitudes (0-1023) in 20-unit steps, matching
the on-device histogram. The modal bin is a rough proxy for the most-probable
energy deposit (the Landau / MIP peak) — no curve-fitting, just the arg_max of
the binned counts (the chosen method per CONTEXT). ADC is uncalibrated, so the
peak position is in raw ADC units, not energy.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")  # headless backend — no DISPLAY on the Pi / CI

import matplotlib.pyplot as plt
import polars as pl
from matplotlib.figure import Figure

# Hyborg sage accent (frontend/src/lib/styles/tokens.css --accent).
_ACCENT = "#6b8e6b"
_NEUTRAL = "#cfcfca"

# Typed empty frame for the C-only / absent-ID safety path.
_HIST_SCHEMA = {"bin_center": pl.Float64, "count": pl.UInt32}


def adc_histogram(df: pl.DataFrame, id: str = "C", bin_width: int = 20) -> pl.DataFrame:
    """Bin ADC values 0-1023 in steps of bin_width. Returns bin_center, count.

    Integer-division binning (``adc // bin_width * bin_width``) is exact and
    stable: 1024/20 -> bins 0, 20, ..., 1020 (the last bin holds 1020-1023).
    ``bin_center`` is ``bin_lo + bin_width/2`` (10, 30, 50, ...). If the
    requested ``id`` has no rows (e.g. asking for T/B on a C-only log), an empty
    typed frame is returned rather than raising.
    """
    sub = df.filter(pl.col("ID") == id)
    if sub.height == 0:
        return pl.DataFrame(schema=_HIST_SCHEMA)
    return (
        sub.with_columns(((pl.col("adc") // bin_width) * bin_width).alias("bin_lo"))
        .group_by("bin_lo")
        .agg(pl.len().alias("count"))
        .sort("bin_lo")
        .with_columns((pl.col("bin_lo") + bin_width / 2).alias("bin_center"))
        .select("bin_center", "count")
    )


def plot_histogram(hist: pl.DataFrame, ax=None) -> Figure:  # type: ignore[no-untyped-def]
    """Plot the ADC histogram, highlighting the modal bin. Returns a matplotlib Figure.

    The modal bin (``count.arg_max()``) is coloured with the sage accent and
    annotated as the MIP / Landau-peak proxy; all other bars are neutral grey.
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=(7, 4.5))
    else:
        fig = ax.figure

    centers = hist["bin_center"].to_list()
    counts = hist["count"].to_list()

    if counts:
        modal_idx = int(hist["count"].arg_max())  # type: ignore[arg-type]
        colors = [_ACCENT if i == modal_idx else _NEUTRAL for i in range(len(counts))]
        width = (centers[1] - centers[0]) * 0.9 if len(centers) >= 2 else 18
        ax.bar(centers, counts, width=width, color=colors, edgecolor="none")
        ax.annotate(
            "MIP peak (modal bin)",
            xy=(centers[modal_idx], counts[modal_idx]),
            xytext=(0, 8),
            textcoords="offset points",
            ha="center",
            fontsize=9,
            color=_ACCENT,
        )

    ax.set_xlabel("ADC (0-1023)")
    ax.set_ylabel("Count")
    ax.set_title("ADC spectrum — coincidence events")
    fig.tight_layout()
    return fig
