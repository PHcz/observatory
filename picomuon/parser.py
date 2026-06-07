"""PicoMuon CSV parser — header metadata + typed event DataFrame.

Strict: a malformed file (bad/short ``###`` header or unexpected columns)
raises :class:`PicoMuonError` and never returns partial data — mirroring the
``observatory/muon/parser.py`` ``ParseError(ValueError)`` discipline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import polars as pl

#: Exact 10-column data header (line 7 of a PicoMuon CSV).
EXPECTED_COLS = [
    "Date",
    "Time",
    "ID",
    "Event",
    "ADC(0-1023)",
    "ElapsedTime(mS)",
    "DeadTime(mS)",
    "Temperature(C)",
    "Pressure(hPa)",
    "DetectorName",
]

_SW_RE = re.compile(r"S/W version:\s*([\d.]+)")
_NAME_RE = re.compile(r"Detector name:\s*(\S+)")
_THRESH_RE = re.compile(
    r"Thresholds:\s*T\(\s*(\d+)\s*,\s*(\d+)\s*\),\s*B\(\s*(\d+)\s*,\s*(\d+)\s*\)"
)


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


def _parse_header(lines: list[str]) -> Metadata:
    """Extract Metadata from the 6 ``###`` header lines; strict on any miss."""
    block = "\n".join(lines)
    sw = _SW_RE.search(block)
    name = _NAME_RE.search(block)
    thresh = _THRESH_RE.search(block)
    if sw is None or name is None or thresh is None:
        raise PicoMuonError("malformed PicoMuon header block")
    return Metadata(
        sw_version=sw.group(1),
        detector_name=name.group(1),
        threshold_t=int(thresh.group(1)),
        reset_t=int(thresh.group(2)),
        threshold_b=int(thresh.group(3)),
        reset_b=int(thresh.group(4)),
    )


def read_csv(path: str | Path) -> tuple[Metadata, pl.DataFrame]:
    """Parse a PicoMuon CSV into (Metadata, typed event DataFrame).

    Combines Date+Time into a datetime column, casts ID to categorical,
    derives elapsed_s/dead_s, and raises PicoMuonError on malformed files.
    """
    raw = Path(path).read_text().splitlines()
    if len(raw) < 8 or not raw[0].startswith("#"):
        raise PicoMuonError("missing/short PicoMuon header")
    meta = _parse_header(raw[:6])
    # Strict ragged-row guard: polars pads short rows with null rather than
    # raising, so validate the raw field count per data line (line 7 = header).
    expected_fields = len(EXPECTED_COLS)
    for line in raw[7:]:
        if not line:
            continue
        if line.count(",") + 1 != expected_fields:
            raise PicoMuonError(
                f"unexpected column count: expected {expected_fields}, got {line.count(',') + 1}"
            )
    try:
        df = pl.read_csv(path, skip_rows=6)
        if df.columns != EXPECTED_COLS:
            raise PicoMuonError(f"unexpected columns: {df.columns}")
        df = df.rename(
            {
                "ADC(0-1023)": "adc",
                "ElapsedTime(mS)": "elapsed_ms",
                "DeadTime(mS)": "dead_ms",
                "Temperature(C)": "temperature_c",
                "Pressure(hPa)": "pressure_hpa",
            }
        ).with_columns(
            (pl.col("Date") + " " + pl.col("Time"))
            .str.to_datetime("%Y-%m-%d %H:%M:%S")
            .alias("datetime"),
            pl.col("ID").cast(pl.Categorical),
            (pl.col("elapsed_ms") / 1000.0).alias("elapsed_s"),
            (pl.col("dead_ms") / 1000.0).alias("dead_s"),
        )
    except PicoMuonError:
        raise
    except (pl.exceptions.PolarsError, ValueError) as exc:
        raise PicoMuonError(f"failed to parse PicoMuon CSV: {exc}") from exc
    return meta, df
