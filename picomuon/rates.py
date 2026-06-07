"""Dead-time-corrected muon rates and flux.

The rate denominator is ALWAYS ``live_s = elapsed_s - dead_s`` (detector-internal
counters), never wall-clock. DeadTime is cumulative in some firmware versions and
per-event in others; the shape is auto-detected by monotonicity (spec Pitfall 1).
Core is DataFrame-in/out so Phase 13 can feed rows read from SQLite.
"""

from __future__ import annotations

import polars as pl

#: PicoMuon scintillator active area, cm2 (50 x 50 mm).
AREA_CM2 = 25.0

#: Exact output schema for bin_rate (empty-frame / C-only-absent path).
_BIN_SCHEMA: dict[str, type[pl.DataType] | pl.DataType] = {
    "bucket_start": pl.Datetime,
    "count": pl.UInt32,
    "elapsed_s": pl.Float64,
    "dead_s": pl.Float64,
    "live_s": pl.Float64,
    "rate_hz": pl.Float64,
    "pressure_mean": pl.Float64,
    "temperature_mean": pl.Float64,
}


def _is_cumulative(sub: pl.DataFrame) -> bool:
    """True if dead_s is non-decreasing over the datetime-sorted frame.

    Cumulative DeadTime is monotone (running total); per-event DeadTime bounces.
    ElapsedTime is always cumulative (detector uptime since file start).
    """
    dead = sub["dead_s"]
    if dead.len() < 2:
        return True
    return bool(dead.is_sorted())


def bin_rate(df: pl.DataFrame, id: str = "C", bucket: str = "10m") -> pl.DataFrame:
    """Bin events into time buckets with dead-time-corrected rate_hz.

    Returns columns bucket_start, count, elapsed_s, dead_s, live_s,
    rate_hz, pressure_mean, temperature_mean. live_s = elapsed_s - dead_s
    is the rate denominator (not wall-clock).
    """
    sub = df.filter(pl.col("ID") == id).sort("datetime")
    if sub.height == 0:
        return pl.DataFrame(schema=_BIN_SCHEMA)

    cumulative = _is_cumulative(sub)
    dead_expr = (
        (pl.col("dead_s").max() - pl.col("dead_s").min()).alias("dead_s")
        if cumulative
        else pl.col("dead_s").sum().alias("dead_s")
    )
    out = (
        sub.group_by_dynamic("datetime", every=bucket, closed="left")
        .agg(
            pl.len().alias("count"),
            (pl.col("elapsed_s").max() - pl.col("elapsed_s").min()).alias("elapsed_s"),
            dead_expr,
            pl.col("pressure_hpa").mean().alias("pressure_mean"),
            pl.col("temperature_c").mean().alias("temperature_mean"),
        )
        .rename({"datetime": "bucket_start"})
        .with_columns((pl.col("elapsed_s") - pl.col("dead_s")).alias("live_s"))
        .with_columns(
            pl.when(pl.col("live_s") > 0)
            .then(pl.col("count") / pl.col("live_s"))
            .otherwise(None)
            .alias("rate_hz")
        )
        .select(
            "bucket_start",
            "count",
            "elapsed_s",
            "dead_s",
            "live_s",
            "rate_hz",
            "pressure_mean",
            "temperature_mean",
        )
    )
    return out


def flux(df: pl.DataFrame, id: str = "C") -> float:
    """Muons per cm² per minute over AREA_CM2, dead-time corrected.

    Live time is taken over the WHOLE file (not per-bucket): ElapsedTime span
    minus total dead time, with the DeadTime shape auto-detected. Per the spec
    fallback, the rightmost row's cumulative dead time is the file total.
    """
    sub = df.filter(pl.col("ID") == id).sort("datetime")
    if sub.height == 0:
        return 0.0

    elapsed_span = float(sub["elapsed_s"].max()) - float(sub["elapsed_s"].min())  # type: ignore[arg-type]
    if _is_cumulative(sub):
        dead_total = float(sub["dead_s"].max()) - float(sub["dead_s"].min())  # type: ignore[arg-type]
    else:
        dead_total = float(sub["dead_s"].sum())
    live_s_total = elapsed_span - dead_total
    if live_s_total <= 0:
        return 0.0

    count_total = sub.height
    return count_total / AREA_CM2 / (live_s_total / 60.0)
