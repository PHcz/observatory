"""Self-contained HTML report builder for the PicoMuon offline CLI.

Renders matplotlib figures to in-memory base64 ``data:`` URIs and assembles a
single Hyborg-themed HTML page with the four analysis plots embedded inline, so
the file opens on any device with no running server. This is the deliverable
artifact that later seeds the Phase 13 dashboard endpoint.

The inline CSS mirrors the Hyborg light theme verbatim
(frontend/src/lib/styles/tokens.css): near-white background, Inter typography,
sage accent ``#6b8e6b``.
"""

from __future__ import annotations

import base64
import html
import io

import matplotlib

matplotlib.use("Agg")  # headless backend — no DISPLAY on the Pi / CI

import matplotlib.pyplot as plt
from matplotlib.figure import Figure

# Hyborg light-theme tokens (frontend/src/lib/styles/tokens.css).
_BG = "#ffffff"
_BG_ELEVATED = "#fafaf8"
_TEXT = "#111111"
_TEXT_MUTED = "#5a5a5a"
_ACCENT = "#6b8e6b"
_BORDER = "#ebebe8"


def fig_to_data_uri(fig: Figure) -> str:
    """Render a matplotlib Figure to a base64 PNG ``data:`` URI and close it.

    The figure is saved to an in-memory buffer (never a temp file), base64
    encoded, and wrapped as ``data:image/png;base64,...`` so it can be embedded
    inline in HTML. The figure is closed afterwards (Pitfall 6 — leaking
    figures exhausts memory over many reports on the Pi).
    """
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _fmt(value: object, *, suffix: str = "", places: int = 2) -> str:
    """Format a number for display, falling back to ``n/a`` for None."""
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{places}f}{suffix}"
    return f"{value}{suffix}"


def build_report_html(
    *,
    meta: object,
    numbers: dict[str, object],
    rate_uri: str,
    pressure_uri: str,
    adc_uri: str,
    temp_or_extra_uri: str,
) -> str:
    """Assemble a single self-contained Hyborg-themed HTML report.

    ``numbers`` is a flat dict of the headline figures (flux, beta, R2, p-value,
    T/B/C totals, runtime, live time). The four ``*_uri`` arguments are base64
    ``data:`` URIs produced by :func:`fig_to_data_uri`. All metadata strings are
    HTML-escaped before interpolation; the base64 payloads are a safe charset.
    """
    detector = html.escape(str(getattr(meta, "detector_name", "unknown")))
    sw_version = html.escape(str(getattr(meta, "sw_version", "unknown")))

    flux = _fmt(numbers.get("flux"), suffix=" /cm²/min", places=3)
    beta = numbers.get("beta")
    beta_str = _fmt(beta, suffix=" %/hPa", places=3)
    r2 = _fmt(numbers.get("r_squared"), places=3)
    p_value = _fmt(numbers.get("p_value"), places=4)
    runtime = _fmt(numbers.get("runtime_s"), suffix=" s", places=0)
    live_time = _fmt(numbers.get("live_s"), suffix=" s", places=0)
    n_t = _fmt(numbers.get("total_t"))
    n_b = _fmt(numbers.get("total_b"))
    n_c = _fmt(numbers.get("total_c"))
    tc_ratio = _fmt(numbers.get("tc_ratio"), places=3)
    bc_ratio = _fmt(numbers.get("bc_ratio"), places=3)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PicoMuon report — {detector}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    background: {_BG};
    color: {_TEXT};
    font-family: Inter, system-ui, sans-serif;
    margin: 0;
    padding: 2rem 1.5rem 4rem;
    line-height: 1.5;
  }}
  .wrap {{ max-width: 880px; margin: 0 auto; }}
  header h1 {{ margin: 0 0 0.25rem; font-size: 1.4rem; font-weight: 600; }}
  header .sub {{ color: {_TEXT_MUTED}; font-size: 0.9rem; }}
  .accent {{ color: {_ACCENT}; }}
  .headline {{ display: flex; gap: 2.5rem; flex-wrap: wrap; margin: 2rem 0; }}
  .headline .metric {{ display: flex; flex-direction: column; }}
  .headline .value {{
    font-size: 2.75rem; font-weight: 700; font-variant-numeric: tabular-nums;
    color: {_ACCENT}; line-height: 1.1;
  }}
  .headline .label {{ color: {_TEXT_MUTED}; font-size: 0.8rem; text-transform: uppercase;
    letter-spacing: 0.04em; }}
  table.numbers {{
    width: 100%; border-collapse: collapse; margin: 1.5rem 0 2.5rem;
    background: {_BG_ELEVATED}; border: 1px solid {_BORDER}; border-radius: 8px;
    overflow: hidden;
  }}
  table.numbers td {{ padding: 0.55rem 1rem; border-bottom: 1px solid {_BORDER};
    font-variant-numeric: tabular-nums; }}
  table.numbers tr:last-child td {{ border-bottom: none; }}
  table.numbers td.k {{ color: {_TEXT_MUTED}; width: 50%; }}
  table.numbers td.v {{ text-align: right; font-weight: 500; }}
  figure {{
    margin: 0 0 2rem; background: {_BG_ELEVATED};
    border: 1px solid {_BORDER}; border-radius: 8px; padding: 1rem;
  }}
  figure img {{ display: block; width: 100%; height: auto; }}
  figure figcaption {{ color: {_TEXT_MUTED}; font-size: 0.85rem; margin-top: 0.5rem; }}
  footer {{ color: {_TEXT_MUTED}; font-size: 0.8rem; margin-top: 2rem;
    border-top: 1px solid {_BORDER}; padding-top: 1rem; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>PicoMuon analysis <span class="accent">report</span></h1>
    <div class="sub">Detector {detector} · firmware {sw_version}</div>
  </header>

  <section class="headline">
    <div class="metric">
      <div class="value">{flux}</div>
      <div class="label">Coincidence flux</div>
    </div>
    <div class="metric">
      <div class="value">{beta_str}</div>
      <div class="label">Barometric β</div>
    </div>
  </section>

  <table class="numbers">
    <tr><td class="k">Total runtime</td><td class="v">{runtime}</td></tr>
    <tr><td class="k">Live time (dead-time corrected)</td><td class="v">{live_time}</td></tr>
    <tr><td class="k">Barometric β</td><td class="v">{beta_str}</td></tr>
    <tr><td class="k">Fit R²</td><td class="v">{r2}</td></tr>
    <tr><td class="k">Fit p-value</td><td class="v">{p_value}</td></tr>
    <tr><td class="k">Top (T) events</td><td class="v">{n_t}</td></tr>
    <tr><td class="k">Bottom (B) events</td><td class="v">{n_b}</td></tr>
    <tr><td class="k">Coincidence (C) events</td><td class="v">{n_c}</td></tr>
    <tr><td class="k">T:C ratio</td><td class="v">{tc_ratio}</td></tr>
    <tr><td class="k">B:C ratio</td><td class="v">{bc_ratio}</td></tr>
  </table>

  <figure>
    <img src="{rate_uri}" alt="Coincidence rate over time with pressure overlay">
    <figcaption>Coincidence rate over time, with atmospheric pressure overlaid.</figcaption>
  </figure>
  <figure>
    <img src="{pressure_uri}" alt="Barometric coefficient fit">
    <figcaption>Barometric fit — ln(rate) vs pressure with 95% CI band.</figcaption>
  </figure>
  <figure>
    <img src="{adc_uri}" alt="ADC histogram for coincidence events">
    <figcaption>ADC spectrum (uncalibrated) — modal bin proxies the MIP peak.</figcaption>
  </figure>
  <figure>
    <img src="{temp_or_extra_uri}" alt="Detector temperature over time">
    <figcaption>Detector internal temperature over the run (BMP280, warm-case).</figcaption>
  </figure>

  <footer>
    Generated by <span class="accent">picomuon</span> · self-contained, no server required.
    ADC is uncalibrated; see README for v1 limitations.
  </footer>
</div>
</body>
</html>
"""
