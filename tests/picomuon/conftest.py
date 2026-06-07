"""Synthesized PicoMuon fixtures for the offline-analysis test suite.

No real detector logs ship with the repo; every fixture is generated here so
tests are deterministic and coordinate-free. Covers the full T/B/C log, the
C-only (events_all=false) variant, and BOTH DeadTime firmware shapes
(cumulative + per-event). A seeded barometric synthetic frame backs the
β-recovery test. matplotlib is forced to the Agg backend so headless test
runs never try to open a display.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import numpy as np
import polars as pl
import pytest

# --- exact wire format (canonical spec §Data schema) -------------------------

COLUMN_HEADER = (
    "Date,Time,ID,Event,ADC(0-1023),ElapsedTime(mS),"
    "DeadTime(mS),Temperature(C),Pressure(hPa),DetectorName"
)


@pytest.fixture(autouse=True)
def _agg_backend() -> None:
    """Belt-and-braces: ensure Agg even if a test imports pyplot first."""
    matplotlib.use("Agg")


def make_picomuon_csv(
    rows: Sequence[str],
    *,
    sw_version: str = "0.1.23",
    detector_name: str = "V56/485",
    thresholds: tuple[int, int, int, int] = (200, 100, 200, 100),
) -> str:
    """Emit a complete PicoMuon CSV string: 6-line ### header + column header + rows.

    ``thresholds`` is (threshold_t, reset_t, threshold_b, reset_b) and is rendered
    into the exact ``### Thresholds: T(200 ,100 ), B(200 ,100 )`` line (line 5).
    ``rows`` are already-formatted comma-joined data lines.
    """
    tt, rt, tb, rb = thresholds
    bar = "#" * 70
    header = [
        bar,
        "### UKRAA: The Pico Muon Detector                                  ###",
        f"### S/W version: {sw_version}{' ' * max(0, 44 - len(sw_version))}###",
        f"### Detector name: {detector_name}{' ' * max(0, 42 - len(detector_name))}###",
        f"### Thresholds: T({tt} ,{rt} ), B({tb} ,{rb} )                         ###",
        bar,
        COLUMN_HEADER,
    ]
    return "\n".join([*header, *rows, ""])


def _build_rows(
    *,
    c_only: bool = False,
    per_event_deadtime: bool = False,
    detector_name: str = "V56/485",
) -> list[str]:
    """Generate ~30+ data rows spanning >=2 ten-minute buckets with a pressure range.

    ElapsedTime is monotonic-cumulative in mS. DeadTime is either cumulative
    (default firmware shape) or small per-event bouncing values.
    """
    rng = np.random.default_rng(2024)
    start = datetime(2025, 1, 24, 10, 21, 4)
    rows: list[str] = []
    elapsed_ms = 0
    dead_cum_ms = 0
    # two buckets ~12 min apart so >=2 ten-minute buckets exist
    offsets_s = [i * 22 for i in range(18)] + [12 * 60 + i * 22 for i in range(18)]
    for i, off in enumerate(offsets_s):
        ts = start + timedelta(seconds=off)
        # pressure ranges across the run (988-998 hPa, lower in 2nd bucket)
        pressure = 996.0 - (off / 60.0) * 0.5
        temp = 20.2 + 0.01 * i
        elapsed_ms += int(900 + rng.integers(0, 400))
        if per_event_deadtime:
            dead_ms = int(rng.integers(0, 8))  # bouncing per-event values
        else:
            dead_cum_ms += int(rng.integers(0, 4))
            dead_ms = dead_cum_ms
        # ADC clustered around a modal bin (~340) so a clear peak exists
        adc = int(np.clip(rng.normal(340, 45), 0, 1023))
        ids = ["C"] if c_only else ["T", "B", "C"]
        for id_ in ids:
            rows.append(
                f"{ts.date()},{ts.strftime('%H:%M:%S')},{id_},{i + 1},"
                f"{adc},{elapsed_ms},{dead_ms},{temp:.1f},{pressure:.1f},{detector_name}"
            )
    return rows


@pytest.fixture
def full_csv(tmp_path: Path) -> Path:
    """Full T/B/C log, cumulative DeadTime, >=2 buckets, pressure range."""
    csv = make_picomuon_csv(_build_rows())
    p = tmp_path / "full.csv"
    p.write_text(csv)
    return p


@pytest.fixture
def c_only_csv(tmp_path: Path) -> Path:
    """C-only log (events_all=false) — no T/B rows."""
    csv = make_picomuon_csv(_build_rows(c_only=True))
    p = tmp_path / "c_only.csv"
    p.write_text(csv)
    return p


@pytest.fixture
def per_event_deadtime_csv(tmp_path: Path) -> Path:
    """Full log but DeadTime is per-event (non-monotonic) — Pitfall 1 shape."""
    csv = make_picomuon_csv(_build_rows(per_event_deadtime=True))
    p = tmp_path / "per_event.csv"
    p.write_text(csv)
    return p


@pytest.fixture
def malformed_bad_header_csv(tmp_path: Path) -> Path:
    """Header block is wrong / missing the column-header line."""
    p = tmp_path / "bad_header.csv"
    p.write_text("not,a,pico,muon,header\n1,2,3,4,5\n")
    return p


@pytest.fixture
def malformed_col_count_csv(tmp_path: Path) -> Path:
    """Valid header but a data row with the wrong number of columns."""
    rows = [
        "2025-01-24,10:21:04,C,1,340,900,0,20.2,996.0",  # 9 cols, missing DetectorName
    ]
    p = tmp_path / "bad_cols.csv"
    p.write_text(make_picomuon_csv(rows))
    return p


def barometric_synthetic(*, beta: float = -0.0018, n: int = 240, seed: int = 12345) -> pl.DataFrame:
    """Binned-shaped frame: rate_hz = base*exp(beta*(P-Pmean)) + gaussian noise.

    ``beta`` is the fractional slope; β in %/hPa = beta*100 (default -0.18).
    Returns columns matching bin_rate output at minimum: pressure_mean, rate_hz.
    """
    rng = np.random.default_rng(seed)
    base = 0.5  # Hz
    pressure = rng.uniform(985.0, 1025.0, n)
    p_mean = float(pressure.mean())
    rate = base * np.exp(beta * (pressure - p_mean))
    rate = rate + rng.normal(0.0, base * 0.01, n)  # small noise
    return pl.DataFrame({"pressure_mean": pressure, "rate_hz": rate})
