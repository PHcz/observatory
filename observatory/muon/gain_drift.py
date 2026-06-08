"""Phase 16 ENH-01 — weekly MIP-peak gain-drift tracking.

Computes a weekly ADC histogram modal bin (MIP-peak proxy) from the last 7
days of coincidence events and upserts one row per ISO week into
muon_weekly_summary.  This gives a detector-health signal: a drifting MIP peak
indicates a hardware gain change (voltage drift, etc.).

The aT effective-temperature correction is DEFERRED.  Do NOT add temperature-
regression code here.
"""

from __future__ import annotations

import datetime
import sqlite3
from typing import Any


def iso_week_start_ts(ts: int) -> int:
    """Return Unix epoch of Monday 00:00 UTC for the ISO week containing ``ts``.

    Args:
        ts: Unix epoch seconds (UTC).

    Returns:
        Unix epoch of Monday 00:00:00 UTC for the week containing ``ts``.
    """
    dt = datetime.datetime.fromtimestamp(ts, tz=datetime.UTC)
    monday = dt - datetime.timedelta(days=dt.weekday())
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(monday.timestamp())


def _rows_to_muon_tuples(rows: list[Any]) -> list[tuple[int, float, float, int]]:
    """Normalise rows to MuonRow tuples (ts, amplitude, pressure, coincidence).

    Accepts either:
    - dict rows (from SQLite sqlite3.Row or plain dict with named keys), or
    - tuples already in MuonRow order (ts, amplitude, detector_pressure_hpa, coincidence).
    """
    result = []
    for r in rows:
        if isinstance(r, dict):
            result.append(
                (
                    int(r["ts"]),
                    float(r["amplitude"]),
                    float(r["detector_pressure_hpa"]),
                    int(r.get("coincidence", 1)),
                )
            )
        else:
            # Already a tuple/sequence in (ts, amplitude, pressure, coincidence) order
            result.append((int(r[0]), float(r[1]), float(r[2]), int(r[3])))
    return result


_MIP_BIN_WIDTH = 20


def compute_mip_peak_adc(rows: list[Any]) -> float | None:
    """Compute the modal ADC bin center (MIP-peak proxy) from muon event rows.

    Uses right-inclusive binning with ``bin_width=20``: ADC value ``a`` is
    assigned to bin ``((a - 1) // 20) * 20``, making the bin ``(bin_lo,
    bin_lo + 20]``.  This matches the test-defined contract where amplitude=340
    falls in bin ``(320, 340]`` (center 330) rather than ``[340, 360)``
    (center 350).

    Args:
        rows: list of muon event rows — either dicts with keys
            ``ts``/``amplitude``/``detector_pressure_hpa``/``coincidence``, or
            tuples in (ts, amplitude, detector_pressure_hpa, coincidence) order.

    Returns:
        Modal ADC bin center (float) if >= 100 rows are provided and the
        histogram is non-empty, else ``None``.
    """
    if len(rows) < 100:
        return None

    import polars as pl

    amplitudes = []
    for r in rows:
        if isinstance(r, dict):
            amplitudes.append(int(r["amplitude"]))
        else:
            amplitudes.append(int(r[1]))

    if not amplitudes:
        return None

    bw = _MIP_BIN_WIDTH
    # Right-inclusive bins: (bin_lo, bin_lo+bw] — amplitude=340 → bin_lo=320.
    bin_lo_list = [((a - 1) // bw) * bw for a in amplitudes]
    df = pl.DataFrame({"bin_lo": bin_lo_list})
    hist = (
        df.group_by("bin_lo")
        .agg(pl.len().alias("count"))
        .sort("bin_lo")
        .with_columns((pl.col("bin_lo") + bw / 2).alias("bin_center"))
        .select("bin_center", "count")
    )
    if hist.height == 0:
        return None
    modal_idx = int(hist["count"].arg_max())
    return float(hist["bin_center"][modal_idx])


def compute_and_store_weekly_mip_peak(conn: sqlite3.Connection, now_ts: int) -> None:
    """Compute the current ISO week's MIP-peak from the last 7d coincidence events.

    Queries ``muon_events`` for coincidence=1 rows in the last 7 days, computes
    the MIP-peak via ``compute_mip_peak_adc``, and UPSERTs one row keyed by
    ``week_start_ts`` (idempotent: re-running for the same week overwrites the
    row with an updated sample).  If ``compute_mip_peak_adc`` returns ``None``
    (< 100 rows or empty histogram), no row is written.

    Args:
        conn: open SQLite connection (caller holds it; this function commits).
        now_ts: current Unix epoch seconds (UTC) — used to derive the week
            boundary and the 7-day look-back window.
    """
    week_start = iso_week_start_ts(now_ts)
    seven_days_ago = now_ts - 7 * 86400

    cursor = conn.execute(
        """
        SELECT ts, amplitude, detector_pressure_hpa, coincidence
        FROM muon_events
        WHERE ts >= ? AND coincidence = 1
        ORDER BY ts ASC
        """,
        (seven_days_ago,),
    )
    rows = [
        {
            "ts": r[0],
            "amplitude": r[1],
            "detector_pressure_hpa": r[2],
            "coincidence": r[3],
        }
        for r in cursor.fetchall()
    ]

    peak = compute_mip_peak_adc(rows)
    if peak is None:
        return

    conn.execute(
        "INSERT INTO muon_weekly_summary(week_start_ts, mip_peak_adc, sample_events, computed_ts)"
        " VALUES (?, ?, ?, ?)"
        " ON CONFLICT(week_start_ts) DO UPDATE SET"
        " mip_peak_adc = excluded.mip_peak_adc,"
        " sample_events = excluded.sample_events,"
        " computed_ts = excluded.computed_ts",
        (week_start, peak, len(rows), now_ts),
    )
    conn.commit()
