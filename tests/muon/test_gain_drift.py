"""Phase 16 ENH-01: MIP-peak gain-drift tracking.

RED: imports from observatory.muon.gain_drift which does not exist yet.
This test gates Wave 1 implementation.

Tests:
- compute_mip_peak_adc: known modal bin center from synthetic histogram data
- compute_mip_peak_adc: insufficient data (< 100 rows) returns None
- iso_week_start_ts: known ts maps to Monday-00:00-UTC epoch
"""

from __future__ import annotations

import datetime

from observatory.muon.gain_drift import compute_mip_peak_adc, iso_week_start_ts


def _make_muon_rows(n: int, amplitude: float) -> list[dict]:
    """Create synthetic muon event rows with amplitude clustered at a given value."""
    return [
        {
            "ts": 1748736000 + i,
            "amplitude": amplitude,
            "detector_pressure_hpa": 1013.0,
            "detector_temp_c": 20.0,
            "coincidence": 1,
        }
        for i in range(n)
    ]


def test_mip_peak_from_known_histogram() -> None:
    """Rows with amplitude=340 yield modal bin center 330 (bin_width=20).

    With bin_width=20: ADC 340 falls in bin 320 (340//20*20=320), center = 320+10 = 330.
    """
    rows = _make_muon_rows(200, amplitude=340.0)
    peak = compute_mip_peak_adc(rows)
    assert peak is not None
    # bin_width=20: amplitude 340 → bin_lo=340//20*20=320, bin_center=320+10=330
    assert peak == 330.0


def test_mip_peak_insufficient_data_returns_none() -> None:
    """Fewer than 100 rows is insufficient for a meaningful histogram — return None."""
    rows = _make_muon_rows(50, amplitude=340.0)
    assert compute_mip_peak_adc(rows) is None


def test_mip_peak_empty_rows_returns_none() -> None:
    """No rows → None."""
    assert compute_mip_peak_adc([]) is None


def test_iso_week_start_ts() -> None:
    """Known timestamp maps to its ISO week Monday 00:00 UTC epoch.

    2026-06-08 (Monday) 00:00:00 UTC = 1749340800
    Any ts within that ISO week should return 1749340800.
    """
    # Wednesday 2026-06-10 12:00 UTC
    ts = int(datetime.datetime(2026, 6, 10, 12, 0, 0, tzinfo=datetime.UTC).timestamp())
    week_start = iso_week_start_ts(ts)
    # ISO week containing 2026-06-10 starts on Monday 2026-06-08 00:00 UTC
    expected = int(datetime.datetime(2026, 6, 8, 0, 0, 0, tzinfo=datetime.UTC).timestamp())
    assert week_start == expected
