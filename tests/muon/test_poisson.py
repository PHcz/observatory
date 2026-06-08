"""Phase 16 ENH-02: Poisson confidence band and anomaly z-score.

RED: imports from observatory.muon.poisson which does not exist yet.
This test gates Wave 1 implementation.

Tests:
- poisson_band: N=100 events in delta_t_sec=60 → rate=100/min, upper=110, lower=90
- anomaly_z_score: known rate, baseline, delta_t_min → exact z value
- anomaly_z_score: guards for baseline<=0 or delta_t_min<=0 → None
"""

from __future__ import annotations

import math

import pytest

from observatory.muon.poisson import anomaly_z_score, poisson_band


def test_poisson_band() -> None:
    """N=100 events in 60s: rate=100/min, +/-1sigma = +/-10/min."""
    result = poisson_band(n=100, delta_t_sec=60)
    # rate = N/Δt * 60 = 100/60*60 = 100.0 events/min
    # sigma = sqrt(N)/Δt * 60 = 10/60*60 = 10.0
    assert result["rate_per_min"] == pytest.approx(100.0, abs=0.01)
    assert result["upper_1sigma"] == pytest.approx(110.0, abs=0.01)
    assert result["lower_1sigma"] == pytest.approx(90.0, abs=0.01)


def test_poisson_band_lower_clamp_at_zero() -> None:
    """Lower band cannot go below 0 when sqrt(N) > N (small N)."""
    result = poisson_band(n=1, delta_t_sec=60)
    assert result["lower_1sigma"] >= 0.0


def test_z_score() -> None:
    """anomaly_z_score(rate=50, baseline=100, delta_t_min=1) == -5.0."""
    # z = (rate - baseline) / sqrt(baseline / delta_t_min)
    # z = (50 - 100) / sqrt(100/1) = -50/10 = -5.0
    result = anomaly_z_score(rate=50.0, baseline=100.0, delta_t_min=1.0)
    assert result == pytest.approx(-5.0, abs=0.001)


def test_z_score_positive() -> None:
    """Positive anomaly: rate above baseline gives positive z."""
    result = anomaly_z_score(rate=130.0, baseline=100.0, delta_t_min=1.0)
    expected = (130.0 - 100.0) / math.sqrt(100.0 / 1.0)
    assert result == pytest.approx(expected, abs=0.001)


def test_z_score_guards_baseline_zero() -> None:
    """baseline=0 → None (guard against division by zero)."""
    assert anomaly_z_score(rate=50.0, baseline=0.0, delta_t_min=1.0) is None


def test_z_score_guards_baseline_negative() -> None:
    """baseline<0 → None."""
    assert anomaly_z_score(rate=50.0, baseline=-1.0, delta_t_min=1.0) is None


def test_z_score_guards_delta_t_zero() -> None:
    """delta_t_min=0 → None."""
    assert anomaly_z_score(rate=50.0, baseline=100.0, delta_t_min=0.0) is None


def test_z_score_guards_delta_t_negative() -> None:
    """delta_t_min<0 → None."""
    assert anomaly_z_score(rate=50.0, baseline=100.0, delta_t_min=-1.0) is None
