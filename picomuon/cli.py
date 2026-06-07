"""Typer CLI: summarise, rate, pressure, adc, report.

Wave 0 stub: command signatures only. Logic lands in Wave 3.

matplotlib.use("Agg") is set BEFORE any pyplot import so the CLI's
plot/report paths render headless on the Pi (no display).
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

from pathlib import Path

import typer

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command()
def summarise(path: Path) -> None:
    """Print flux, runtime, live time, T/B/C totals, and T:C / B:C ratios."""
    raise NotImplementedError


@app.command()
def rate(
    path: Path,
    bucket: str = "10m",
    out: Path = typer.Option(Path("rate.png"), "--out"),
) -> None:
    """Plot coincidence rate over time with overlaid pressure."""
    raise NotImplementedError


@app.command()
def pressure(
    path: Path,
    out: Path = typer.Option(Path("pressure.png"), "--out"),
) -> None:
    """Plot the barometric fit (rate vs pressure)."""
    raise NotImplementedError


@app.command()
def adc(
    path: Path,
    out: Path = typer.Option(Path("adc.png"), "--out"),
) -> None:
    """Plot the ADC histogram for coincidence events."""
    raise NotImplementedError


@app.command()
def report(
    path: Path,
    out: Path = typer.Option(Path("report.html"), "--out"),
) -> None:
    """Render a self-contained HTML report (inline base64 PNGs + numbers)."""
    raise NotImplementedError


if __name__ == "__main__":
    app()
