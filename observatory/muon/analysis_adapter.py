"""muon_events -> picomuon analysis adapter (Phase 13, MU2-05).

Reshapes muon_events rows (ts/amplitude/detector_pressure_hpa/coincidence) into
the polars frames the Phase-12 ``picomuon`` core reads:

  - ``adc_histogram`` reads only ``ID`` + ``adc``
  - ``barometric_fit`` reads only ``rate_hz`` + ``pressure_mean``

The live rate is WALL-CLOCK (``count / bucket_seconds``) with NO dead-time
correction. ``muon_events`` has no dead-time / elapsed field (unlike the
PicoMuon CSV), so the Phase-12 rate helper that needs those columns is
deliberately NOT used here — reusing it would require fabricating live-time
fields and would silently claim a dead-time correction the live path must not
promise. The offline CLI (Phase 12) stays the dead-time-corrected source of
truth; the live panels are labelled "raw — not dead-time corrected".

The module is pure (DataFrame-in/out, no FastAPI / SQLite import) so it
unit-tests without the API. ``polars`` and the ``picomuon`` core (polars+scipy)
are imported at module load here; the API route lazy-imports this module so a
missing ``[analysis]`` extra degrades to an empty-state 200 rather than a 500.
"""

from __future__ import annotations

import polars as pl

from picomuon.histogram import adc_histogram
from picomuon.pressure import BarometricFit, barometric_fit

# A muon_events row is (ts_epoch_s, amplitude, detector_pressure_hpa, coincidence).
MuonRow = tuple[int, float, float, int]

# A barometric fit needs several buckets across a real pressure range; below this
# we return None (UI empty-state) rather than a meaningless one/two-point fit.
MIN_BUCKETS = 5

# ADC histogram empty-state schema (mirrors picomuon.histogram._HIST_SCHEMA).
_HIST_SCHEMA = {"bin_center": pl.Float64, "count": pl.UInt32}


def build_adc_frame(rows: list[MuonRow]) -> pl.DataFrame:
    """Reshape muon_events rows into a frame with constant ``ID="C"`` + ``adc``.

    Rows are assumed already filtered to coincidence events (SQL ``coincidence =
    1``); amplitudes are cast to int so ``adc_histogram``'s integer-division
    binning is exact. Empty input -> a typed empty frame.
    """
    amplitudes = [int(r[1]) for r in rows]
    n = len(amplitudes)
    return pl.DataFrame(
        {"ID": ["C"] * n, "adc": amplitudes},
        schema={"ID": pl.Utf8, "adc": pl.Int64},
    )


def build_barometric_frame(rows: list[MuonRow], bucket_seconds: int = 3600) -> pl.DataFrame:
    """Bucket rows into a frame with wall-clock ``rate_hz`` + ``pressure_mean``.

    Groups events into fixed wall-clock windows (default 1h), counts events per
    bucket, takes the mean detector pressure, then derives ``rate_hz = count /
    bucket_seconds`` — a RAW wall-clock rate with NO dead-time correction
    (muon_events lacks the field). The frame carries exactly the two columns
    ``barometric_fit`` reads (``rate_hz`` + ``pressure_mean``).
    """
    if not rows:
        return pl.DataFrame(
            schema={
                "datetime": pl.Datetime,
                "count": pl.UInt32,
                "pressure_mean": pl.Float64,
                "rate_hz": pl.Float64,
            }
        )

    df = pl.DataFrame(
        {
            "datetime": pl.from_epoch(pl.Series([r[0] for r in rows]), time_unit="s"),
            "pressure_hpa": [r[2] for r in rows],
        }
    )
    every = f"{bucket_seconds}s"
    return (
        df.sort("datetime")
        .group_by_dynamic("datetime", every=every, closed="left")
        .agg(
            pl.len().alias("count"),
            pl.col("pressure_hpa").mean().alias("pressure_mean"),
        )
        # RAW wall-clock rate (Hz) — NO dead-time correction (honesty line).
        .with_columns((pl.col("count") / float(bucket_seconds)).alias("rate_hz"))
    )


def live_adc_histogram(rows: list[MuonRow]) -> pl.DataFrame:
    """ADC histogram (bin_center, count) over the muon_events window."""
    if not rows:
        return pl.DataFrame(schema=_HIST_SCHEMA)
    return adc_histogram(build_adc_frame(rows), id="C", bin_width=20)


def live_barometric(
    rows: list[MuonRow], bucket_seconds: int = 3600, min_buckets: int = MIN_BUCKETS
) -> BarometricFit | None:
    """Barometric fit over the muon_events window, or ``None`` on thin data.

    Returns ``None`` (UI empty-state, never a crash) when there are too few
    usable buckets (< ``min_buckets``) or no pressure variation (fewer than two
    distinct ``pressure_mean`` values) — both make the regression meaningless.
    """
    if not rows:
        return None
    frame = build_barometric_frame(rows, bucket_seconds=bucket_seconds)
    usable = frame.filter(pl.col("rate_hz").is_not_null() & (pl.col("rate_hz") > 0))
    if usable.height < min_buckets:
        return None
    if usable["pressure_mean"].drop_nulls().n_unique() < 2:
        return None
    return barometric_fit(usable)
