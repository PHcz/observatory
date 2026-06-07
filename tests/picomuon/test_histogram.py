"""RED scaffolds for picomuon.histogram (Wave 2 turns these GREEN)."""

from __future__ import annotations

from pathlib import Path

from picomuon.histogram import adc_histogram
from picomuon.parser import read_csv


def test_adc_histogram_bins(full_csv: Path) -> None:
    _, df = read_csv(full_csv)
    hist = adc_histogram(df, id="C", bin_width=20)
    assert "bin_center" in hist.columns
    assert "count" in hist.columns
    centers = hist["bin_center"].to_list()
    assert all(0 <= c <= 1023 for c in centers)
    # bin width 20: adjacent centers differ by 20
    if len(centers) >= 2:
        assert centers[1] - centers[0] == 20


def test_adc_histogram_modal(full_csv: Path) -> None:
    _, df = read_csv(full_csv)
    hist = adc_histogram(df, id="C", bin_width=20)
    counts = hist["count"].to_list()
    # AC#3: non-flat distribution with a clear modal bin
    assert max(counts) > min(counts)
    modal_idx = counts.index(max(counts))
    modal_center = hist["bin_center"].to_list()[modal_idx]
    # modal bin is the arg_max of count and sits within ADC range
    assert 0 <= modal_center <= 1023
