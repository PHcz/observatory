"""RED scaffolds for picomuon.pressure (Wave 2 turns these GREEN)."""

from __future__ import annotations

from picomuon.pressure import BarometricFit, barometric_fit

from .conftest import barometric_synthetic


def test_barometric_fit_recover_beta() -> None:
    # AC#2: recover β_true = -0.18 %/hPa within ±0.02 on N>=200 seeded buckets.
    binned = barometric_synthetic(beta=-0.0018, n=240, seed=12345)
    fit = barometric_fit(binned)
    assert isinstance(fit, BarometricFit)
    # fit.beta is the barometric coefficient in %/hPa
    assert -0.20 <= fit.beta <= -0.16


def test_barometric_fit_stats() -> None:
    binned = barometric_synthetic(beta=-0.0018, n=240, seed=999)
    fit = barometric_fit(binned)
    assert 0.0 <= fit.r_squared <= 1.0
    assert fit.p_value is not None
    assert fit.n > 0
    # fit filters to rate > 0 before taking ln
    assert fit.n <= binned.height
