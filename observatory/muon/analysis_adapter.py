"""muon_events -> picomuon analysis adapter (Phase 13, MU2-05).

Wave-0 RED skeleton: every function raises NotImplementedError. Wave 1 (plan
13-02) implements the column adapter that reshapes muon_events rows
(ts/amplitude/detector_pressure_hpa/coincidence) into the polars frames the
Phase-12 ``picomuon`` core reads, and the ``live_*`` wrappers.

The live rate is WALL-CLOCK (count / bucket_seconds) with NO dead-time correction
(muon_events lacks the field) — the locked honesty contract. The offline CLI
(Phase 12) stays the dead-time-corrected source of truth.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # avoid importing the heavy polars/scipy stack at module load
    import polars as pl

    from picomuon.pressure import BarometricFit

# A muon_events row is (ts_epoch_s, amplitude, detector_pressure_hpa, coincidence).
MuonRow = tuple[int, float, float, int]


def build_adc_frame(rows: list[MuonRow]) -> pl.DataFrame:
    """Reshape muon_events rows into a polars frame with ID + adc columns.

    Implemented in Wave 1 (plan 13-02).
    """
    raise NotImplementedError("build_adc_frame is implemented in Wave 1 (plan 13-02)")


def build_barometric_frame(rows: list[MuonRow], bucket_seconds: int) -> pl.DataFrame:
    """Bucket muon_events rows into a frame with wall-clock rate_hz + pressure_mean.

    Implemented in Wave 1 (plan 13-02).
    """
    raise NotImplementedError("build_barometric_frame is implemented in Wave 1 (plan 13-02)")


def live_adc_histogram(rows: list[MuonRow]) -> pl.DataFrame:
    """ADC histogram (bin_center, count) over the muon_events window.

    Implemented in Wave 1 (plan 13-02).
    """
    raise NotImplementedError("live_adc_histogram is implemented in Wave 1 (plan 13-02)")


def live_barometric(rows: list[MuonRow], bucket_seconds: int) -> BarometricFit | None:
    """Barometric fit over the muon_events window, or None on thin data.

    Implemented in Wave 1 (plan 13-02).
    """
    raise NotImplementedError("live_barometric is implemented in Wave 1 (plan 13-02)")
