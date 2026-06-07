"""Typer CLI: summarise, rate, pressure, adc, report.

The offline user-facing surface for the PicoMuon analysis core (MU2-04).
``summarise`` prints a clean aligned text table (no rich dependency); the plot
commands write a PNG to a sensible CWD default; ``report`` emits a single
self-contained Hyborg-themed HTML with the four plots inlined as base64 PNGs so
it opens on any device with no running server. Malformed CSV is caught as a
typed PicoMuonError → one-line stderr message + non-zero exit (no silent
row-skipping).

matplotlib.use("Agg") is set BEFORE any pyplot import so the CLI's
plot/report paths render headless on the Pi (no display).
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

from pathlib import Path

import matplotlib.pyplot as plt
import polars as pl
import typer
from matplotlib.figure import Figure

from picomuon import report as report_mod
from picomuon.histogram import adc_histogram, plot_histogram
from picomuon.parser import Metadata, PicoMuonError, read_csv
from picomuon.pressure import barometric_fit, plot_fit
from picomuon.rates import AREA_CM2, bin_rate, flux

# Hyborg sage accent (frontend/src/lib/styles/tokens.css --accent).
_ACCENT = "#6b8e6b"

app = typer.Typer(no_args_is_help=True, add_completion=False)


def _load(path: Path) -> tuple[Metadata, pl.DataFrame]:
    """Parse a PicoMuon CSV, turning a typed parse error into a clean CLI exit.

    Every command routes through this so a malformed file surfaces as a
    one-line stderr message + exit code 1 (never a traceback, never partial
    data).
    """
    try:
        return read_csv(path)
    except PicoMuonError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def _count(df: pl.DataFrame, id: str) -> int:
    """Number of rows for an ID stream (T/B/C)."""
    return df.filter(pl.col("ID") == id).height


def _ratio(numer: int, denom: int) -> float | None:
    """numer/denom, or None when either side is zero (rendered ``n/a``).

    A zero numerator means that scintillator stream is absent (the C-only
    ``events_all=false`` log has no T/B rows), so the ratio is meaningless
    rather than literally 0.0; a zero denominator is undefined.
    """
    if denom == 0 or numer == 0:
        return None
    return numer / denom


def _runtime_s(df: pl.DataFrame) -> float:
    """Total runtime: ElapsedTime span over the whole file (seconds)."""
    if df.height == 0:
        return 0.0
    span = float(df["elapsed_s"].max()) - float(df["elapsed_s"].min())  # type: ignore[arg-type]
    return max(span, 0.0)


def _live_s(df: pl.DataFrame, id: str = "C") -> float:
    """Dead-time-corrected live time for an ID stream (seconds)."""
    binned = bin_rate(df, id=id)
    if binned.height == 0:
        return 0.0
    return float(binned["live_s"].sum())


def _rate_figure(df: pl.DataFrame, bucket: str) -> Figure:
    """Coincidence rate over time with an overlaid pressure trace (twin axis)."""
    binned = bin_rate(df, id="C", bucket=bucket).filter(pl.col("rate_hz").is_not_null())
    fig, ax = plt.subplots(figsize=(8, 4.5))
    x = binned["bucket_start"].to_list()
    ax.plot(
        x,
        binned["rate_hz"].to_list(),
        color=_ACCENT,
        lw=1.6,
        marker="o",
        ms=3,
        label="coincidence rate",
    )
    ax.set_xlabel("Time")
    ax.set_ylabel("Rate (Hz)", color=_ACCENT)
    ax.tick_params(axis="y", labelcolor=_ACCENT)
    ax.set_title("Coincidence rate over time")
    ax2 = ax.twinx()
    ax2.plot(
        x, binned["pressure_mean"].to_list(), color="#5a5a5a", lw=1.2, ls="--", label="pressure"
    )
    ax2.set_ylabel("Pressure (hPa)", color="#5a5a5a")
    ax2.tick_params(axis="y", labelcolor="#5a5a5a")
    fig.autofmt_xdate()
    fig.tight_layout()
    return fig


def _pressure_figure(df: pl.DataFrame) -> Figure:
    """Barometric fit figure (rate vs pressure with regression + CI band)."""
    binned = bin_rate(df, id="C")
    fit = barometric_fit(binned)
    return plot_fit(fit, binned)


def _adc_figure(df: pl.DataFrame) -> Figure:
    """ADC histogram figure for coincidence events."""
    hist = adc_histogram(df, id="C")
    return plot_histogram(hist)


def _temperature_figure(df: pl.DataFrame) -> Figure:
    """Detector internal temperature over time (supplementary, fourth plot)."""
    sub = df.filter(pl.col("ID") == "C").sort("datetime")
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(sub["datetime"].to_list(), sub["temperature_c"].to_list(), color=_ACCENT, lw=1.4)
    ax.set_xlabel("Time")
    ax.set_ylabel("Temperature (°C)")
    ax.set_title("Detector internal temperature (BMP280, warm-case)")
    fig.autofmt_xdate()
    fig.tight_layout()
    return fig


@app.command()
def summarise(path: Path) -> None:
    """Print flux, runtime, live time, T/B/C totals, and T:C / B:C ratios."""
    _meta, df = _load(path)

    flux_val = flux(df, id="C")
    runtime = _runtime_s(df)
    live = _live_s(df, id="C")
    n_t = _count(df, "T")
    n_b = _count(df, "B")
    n_c = _count(df, "C")
    tc = _ratio(n_t, n_c)
    bc = _ratio(n_b, n_c)

    def _r(v: float | None) -> str:
        return "n/a" if v is None else f"{v:.3f}"

    rows: list[tuple[str, str]] = [
        ("flux (/cm²/min)", f"{flux_val:.3f}"),
        ("active area (cm²)", f"{AREA_CM2:.1f}"),
        ("total runtime (s)", f"{runtime:.0f}"),
        ("live time (s)", f"{live:.0f}"),
        ("T events", str(n_t)),
        ("B events", str(n_b)),
        ("C events", str(n_c)),
        ("T:C ratio", _r(tc)),
        ("B:C ratio", _r(bc)),
    ]
    lines = [f"{label:<22}{value:>14}" for label, value in rows]
    typer.echo("\n".join(lines))


@app.command()
def rate(
    path: Path,
    bucket: str = "10m",
    out: Path = typer.Option(Path("rate.png"), "--out"),
) -> None:
    """Plot coincidence rate over time with overlaid pressure."""
    _meta, df = _load(path)
    fig = _rate_figure(df, bucket)
    fig.savefig(out, dpi=120, bbox_inches="tight")
    plt.close(fig)
    typer.echo(f"wrote {out}")


@app.command()
def pressure(
    path: Path,
    out: Path = typer.Option(Path("pressure.png"), "--out"),
) -> None:
    """Plot the barometric fit (rate vs pressure)."""
    _meta, df = _load(path)
    fig = _pressure_figure(df)
    fig.savefig(out, dpi=120, bbox_inches="tight")
    plt.close(fig)
    typer.echo(f"wrote {out}")


@app.command()
def adc(
    path: Path,
    out: Path = typer.Option(Path("adc.png"), "--out"),
) -> None:
    """Plot the ADC histogram for coincidence events."""
    _meta, df = _load(path)
    fig = _adc_figure(df)
    fig.savefig(out, dpi=120, bbox_inches="tight")
    plt.close(fig)
    typer.echo(f"wrote {out}")


@app.command()
def report(
    path: Path,
    out: Path = typer.Option(Path("report.html"), "--out"),
) -> None:
    """Render a self-contained HTML report (inline base64 PNGs + numbers)."""
    meta, df = _load(path)

    binned = bin_rate(df, id="C")
    fit = barometric_fit(binned)

    n_t = _count(df, "T")
    n_b = _count(df, "B")
    n_c = _count(df, "C")
    numbers: dict[str, object] = {
        "flux": flux(df, id="C"),
        "beta": fit.beta,
        "r_squared": fit.r_squared,
        "p_value": fit.p_value,
        "runtime_s": _runtime_s(df),
        "live_s": _live_s(df, id="C"),
        "total_t": n_t,
        "total_b": n_b,
        "total_c": n_c,
        "tc_ratio": _ratio(n_t, n_c),
        "bc_ratio": _ratio(n_b, n_c),
    }

    rate_uri = report_mod.fig_to_data_uri(_rate_figure(df, "10m"))
    pressure_uri = report_mod.fig_to_data_uri(plot_fit(fit, binned))
    adc_uri = report_mod.fig_to_data_uri(_adc_figure(df))
    temp_uri = report_mod.fig_to_data_uri(_temperature_figure(df))

    html_doc = report_mod.build_report_html(
        meta=meta,
        numbers=numbers,
        rate_uri=rate_uri,
        pressure_uri=pressure_uri,
        adc_uri=adc_uri,
        temp_or_extra_uri=temp_uri,
    )
    out.write_text(html_doc)
    typer.echo(f"wrote {out}")


if __name__ == "__main__":
    app()
