"""picomuon — offline analysis for the UKRAA PicoMuon cosmic ray detector."""

from __future__ import annotations

from picomuon.histogram import adc_histogram
from picomuon.parser import Metadata, PicoMuonError, read_csv
from picomuon.pressure import BarometricFit, barometric_fit
from picomuon.rates import bin_rate, flux

__version__ = "0.1.0"

__all__ = [
    "BarometricFit",
    "Metadata",
    "PicoMuonError",
    "adc_histogram",
    "barometric_fit",
    "bin_rate",
    "flux",
    "read_csv",
]
