"""PicoMuon CSV parser — header metadata + typed event DataFrame.

Wave 0 stub: locked signatures only. Logic lands in Wave 1.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import polars as pl


class PicoMuonError(ValueError):
    """Malformed PicoMuon CSV (bad header, wrong column count)."""


@dataclass(frozen=True, slots=True)
class Metadata:
    """Parsed 6-line PicoMuon header block."""

    sw_version: str
    detector_name: str
    threshold_t: int
    reset_t: int
    threshold_b: int
    reset_b: int


def read_csv(path: str | Path) -> tuple[Metadata, pl.DataFrame]:
    """Parse a PicoMuon CSV into (Metadata, typed event DataFrame).

    Combines Date+Time into a datetime column, casts ID to categorical,
    and raises PicoMuonError on malformed files.
    """
    raise NotImplementedError
