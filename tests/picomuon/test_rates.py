"""RED scaffolds for picomuon.rates (Wave 1 turns these GREEN)."""

from __future__ import annotations

from pathlib import Path

import pytest

from picomuon.parser import read_csv
from picomuon.rates import bin_rate, flux


def test_bin_rate_buckets_and_live_s(full_csv: Path) -> None:
    _, df = read_csv(full_csv)
    binned = bin_rate(df, id="C", bucket="10m")
    # >=2 ten-minute buckets in the fixture
    assert binned.height >= 2
    for col in ("bucket_start", "count", "elapsed_s", "dead_s", "live_s", "rate_hz"):
        assert col in binned.columns
    row = binned.row(0, named=True)
    # live_s == elapsed_s - dead_s
    assert row["live_s"] == pytest.approx(row["elapsed_s"] - row["dead_s"], rel=1e-6)
    # rate_hz == count / live_s
    assert row["rate_hz"] == pytest.approx(row["count"] / row["live_s"], rel=1e-6)


def test_deadtime_cumulative_vs_per_event(full_csv: Path, per_event_deadtime_csv: Path) -> None:
    _, df_cum = read_csv(full_csv)
    _, df_pe = read_csv(per_event_deadtime_csv)
    for df in (df_cum, df_pe):
        binned = bin_rate(df, id="C", bucket="10m")
        # both DeadTime shapes yield sane, positive live_s <= elapsed_s
        for r in binned.iter_rows(named=True):
            assert r["live_s"] > 0
            assert r["live_s"] <= r["elapsed_s"]


def test_flux_order_of_magnitude(full_csv: Path) -> None:
    _, df = read_csv(full_csv)
    f = flux(df, id="C")  # muons / cm² / min
    # AC#1: within an order of magnitude of 1 muon/cm²/min
    assert 0.1 <= f <= 10.0


def test_flux_c_only(c_only_csv: Path) -> None:
    _, df = read_csv(c_only_csv)
    f = flux(df, id="C")
    assert f > 0
