"""RED tests for the muon_events -> picomuon analysis adapter (Phase 13, MU2-05).

These import build_adc_frame / build_barometric_frame / live_adc_histogram /
live_barometric from observatory.muon.analysis_adapter, which Wave 1 (plan 13-02)
creates. Until then these fail at import (expected RED).

The adapter reshapes muon_events rows (ts/amplitude/detector_pressure_hpa/coincidence)
into the polars frames the Phase-12 picomuon core reads:
  - adc_histogram reads ID + adc
  - barometric_fit reads rate_hz + pressure_mean

Live rate is WALL-CLOCK (count / bucket_seconds) — NO dead-time correction
(muon_events has no dead-time field). This is the locked honesty contract.
"""

from __future__ import annotations

from observatory.muon.analysis_adapter import (
    build_adc_frame,
    build_barometric_frame,
    live_adc_histogram,
    live_barometric,
    live_barometric_points,
)

# A muon_events-shaped row sequence: (ts_epoch_s, amplitude, detector_pressure_hpa, coincidence)
# Spread across several hourly buckets with a pressure range so barometric_fit has signal.
_BUCKET = 3600
_T0 = 1_700_000_000


def _rows(n_buckets: int = 6, per_bucket: int = 40) -> list[tuple[int, float, float, int]]:
    rows: list[tuple[int, float, float, int]] = []
    for b in range(n_buckets):
        # Pressure walks across a real range so linregress is well-defined.
        pressure = 1000.0 + b * 2.0
        for i in range(per_bucket):
            ts = _T0 + b * _BUCKET + i
            amplitude = 320.0 + (i % 20)
            rows.append((ts, amplitude, pressure, 1))
    return rows


def test_build_adc_frame_has_id_and_adc_columns() -> None:
    frame = build_adc_frame(_rows())
    assert "ID" in frame.columns
    assert "adc" in frame.columns
    # Synthesised constant ID="C" for coincidence rows.
    assert set(frame["ID"].to_list()) == {"C"}


def test_build_barometric_frame_has_rate_and_pressure_columns() -> None:
    frame = build_barometric_frame(_rows(), bucket_seconds=_BUCKET)
    assert "rate_hz" in frame.columns
    assert "pressure_mean" in frame.columns


def test_rate_is_wall_clock_not_dead_time_corrected() -> None:
    # 40 events in a 3600s bucket -> wall-clock rate_hz = 40/3600.
    frame = build_barometric_frame(_rows(n_buckets=1, per_bucket=40), bucket_seconds=_BUCKET)
    rates = [r for r in frame["rate_hz"].to_list() if r is not None]
    assert rates, "expected at least one bucket with a rate"
    assert abs(rates[0] - (40.0 / 3600.0)) < 1e-9


def test_live_adc_histogram_returns_bin_center_and_count() -> None:
    hist = live_adc_histogram(_rows())
    assert "bin_center" in hist.columns
    assert "count" in hist.columns


def test_live_barometric_returns_fit_on_real_pressure_range() -> None:
    fit = live_barometric(_rows(), bucket_seconds=_BUCKET)
    assert fit is not None
    # BarometricFit carries beta / r_squared / p_value / n (Phase-12 contract).
    assert hasattr(fit, "beta")
    assert hasattr(fit, "r_squared")
    assert hasattr(fit, "n")


def test_live_barometric_returns_none_on_too_few_buckets() -> None:
    # A single bucket -> no pressure range -> cannot fit -> None (UI empty-state).
    assert live_barometric(_rows(n_buckets=1, per_bucket=40), bucket_seconds=_BUCKET) is None


def test_live_barometric_returns_none_on_empty_rows() -> None:
    assert live_barometric([], bucket_seconds=_BUCKET) is None


def test_live_barometric_points_match_fit_buckets() -> None:
    # When a fit is returned, points are a non-empty list of
    # {pressure_hpa, rate_per_min} — one per usable bucket (root cause 2).
    points = live_barometric_points(_rows(), bucket_seconds=_BUCKET)
    fit = live_barometric(_rows(), bucket_seconds=_BUCKET)
    assert fit is not None
    assert points, "expected non-empty scatter points when a fit exists"
    assert len(points) == fit.n
    for pt in points:
        assert set(pt) == {"pressure_hpa", "rate_per_min"}
    # rate_per_min = rate_hz * 60 = (per_bucket / bucket_seconds) * 60.
    assert abs(points[0]["rate_per_min"] - (40.0 / _BUCKET) * 60.0) < 1e-3


def test_live_barometric_points_empty_on_thin_data() -> None:
    assert live_barometric_points(_rows(n_buckets=1, per_bucket=40), bucket_seconds=_BUCKET) == []
    assert live_barometric_points([], bucket_seconds=_BUCKET) == []
