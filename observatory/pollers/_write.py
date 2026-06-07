"""Dedup-aware writer + separate-transaction poller_runs emit + parse-outcome helper.

Two transactions (events INSERT, then poller_runs INSERT) so the audit
row survives any event-write rollback (CONTEXT Open Question 4 / Pitfall 10).
"""

from __future__ import annotations

import sqlite3
import time

import structlog

from observatory.config import settings
from observatory.db.connection import get_write_conn
from observatory.pollers._types import (
    AirQualitySnapshot,
    AuroraSnapshot,
    EarthquakeEvent,
    ForecastDaily,
    ForecastHourly,
    LightningStrike,
    NmdbCount,
    SpaceWeatherSnapshot,
)

log = structlog.get_logger(__name__)


def compute_parse_outcome(
    good: int,
    failures: int,
    threshold: float | None = None,
) -> tuple[str, str | None]:
    """Decide poller exit status from per-item parse results.

    Implements the CONTEXT-locked partial-parse contract:
      - 10 fetched, 8 parse cleanly -> ('success', None); caller writes the 8
      - failure ratio EXCEEDS threshold -> ('parse_fail', summary); caller writes 0

    Boundary semantics: ratio == threshold is NOT a failure (CONTEXT
    wording is "exceeds 50%", strict greater-than).
    Empty fetch (good == failures == 0) is success — legitimate quiet period.

    Returns (status, error_summary). Summary is None on success, else a
    short human-readable string e.g. 'parse_fail_ratio=0.80 (8/10)'.
    """
    if threshold is None:
        threshold = settings.poller_parse_failure_threshold
    total = good + failures
    if total == 0:
        return ("success", None)
    ratio = failures / total
    if ratio > threshold:
        summary = f"parse_fail_ratio={ratio:.2f} ({failures}/{total})"
        return ("parse_fail", summary)
    return ("success", None)


def write_events(
    source: str,
    events: list[EarthquakeEvent],
    started_at: int,
    status: str,
    error_summary: str | None = None,
) -> tuple[int, int]:
    """Write events with INSERT OR IGNORE and emit one poller_runs row.

    Uses TWO transactions so the audit row lands even if the events
    transaction rolls back (Pitfall 10 in 04-RESEARCH).

    Returns (fetched, written).
    """
    fetched = len(events)
    written = 0
    events_status = status
    events_error = error_summary

    # --- Transaction 1: event inserts (best-effort) ---
    if events:
        try:
            with get_write_conn() as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    for ev in events:
                        cur = conn.execute(
                            "INSERT OR IGNORE INTO earthquakes "
                            "(source, external_id, ts, magnitude, depth_km, "
                            "latitude, longitude, place, is_local) "
                            "VALUES (?,?,?,?,?,?,?,?,?)",
                            (
                                ev.source,
                                ev.external_id,
                                ev.ts,
                                ev.magnitude,
                                ev.depth_km,
                                ev.latitude,
                                ev.longitude,
                                ev.place,
                                int(ev.is_local),  # bool -> 0/1 for SQLite INTEGER (UI-18)
                            ),
                        )
                        written += cur.rowcount  # 1 on insert, 0 on ignore (dedup)
                    conn.execute("COMMIT")
                except Exception:
                    conn.execute("ROLLBACK")
                    raise
        except (sqlite3.Error, sqlite3.ProgrammingError, sqlite3.InterfaceError) as exc:
            events_status = "db_fail"
            events_error = f"{type(exc).__name__}: {exc}"
            written = 0
            log.error("write_events_db_failure", source=source, error=str(exc))

    # --- Transaction 2: audit row (always attempted) ---
    ended_at = int(time.time())
    try:
        with get_write_conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT INTO poller_runs "
                "(source, started_at, ended_at, status, events_fetched, "
                "events_written, error_summary) VALUES (?,?,?,?,?,?,?)",
                (
                    source,
                    started_at,
                    ended_at,
                    events_status,
                    fetched,
                    written,
                    events_error[:200] if events_error else None,
                ),
            )
            conn.execute("COMMIT")
    except sqlite3.Error as exc:
        log.error("poller_runs_emit_failed", source=source, error=str(exc))

    if events and written < fetched and events_status == "success":
        log.info(
            "dedup_skipped",
            source=source,
            skipped=fetched - written,
            fetched=fetched,
            written=written,
        )
    return fetched, written


def write_space_weather(
    snapshot: SpaceWeatherSnapshot | None,
    started_at: int,
    status: str,
    error_summary: str | None = None,
) -> tuple[int, int]:
    """Write 0 or 1 ``space_weather`` rows + always emit one ``poller_runs`` row (POLL-04).

    Mirrors :func:`write_events` / :func:`write_aurora_status` two-transaction
    discipline (snapshot insert + audit insert kept separate so the audit
    row survives any rollback of the snapshot insert).

    NOAA-specific: introduces ``status='partial'`` to the ``poller_runs``
    status vocabulary, meaning 1 or 2 of NOAA's 3 endpoints succeeded.
    The /api/health endpoint (Plan 05-05) treats ``partial`` as non-fatal
    (the source is healthy from the data-freshness perspective).

    Args:
      snapshot: per-poll snapshot, or ``None`` when all 3 endpoints
        failed and caller is recording a ``transient_fail``.
      started_at: poll start time (unix epoch seconds).
      status: ``'success'`` | ``'partial'`` | ``'transient_fail'`` |
        ``'parse_fail'`` | ``'db_fail'``.
      error_summary: short human-readable summary; truncated to 200
        chars at write time.

    Returns:
      ``(fetched, written)`` — both 0 or 1 for noaa. No dedup applied;
      every poll writes a fresh row.
    """
    source = "noaa"
    fetched = 0 if snapshot is None else 1
    written = 0
    events_status = status
    events_error = error_summary

    # --- Transaction 1: snapshot insert (best-effort) ---
    if snapshot is not None:
        try:
            with get_write_conn() as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    cur = conn.execute(
                        "INSERT INTO space_weather "
                        "(ts, kp_index, solar_wind_kms, flare_class, flare_peak_ts) "
                        "VALUES (?,?,?,?,?)",
                        (
                            snapshot.ts,
                            snapshot.kp_index,
                            snapshot.solar_wind_kms,
                            snapshot.flare_class,
                            snapshot.flare_peak_ts,
                        ),
                    )
                    written = cur.rowcount
                    conn.execute("COMMIT")
                except Exception:
                    conn.execute("ROLLBACK")
                    raise
        except (sqlite3.Error, sqlite3.ProgrammingError, sqlite3.InterfaceError) as exc:
            events_status = "db_fail"
            events_error = f"{type(exc).__name__}: {exc}"
            written = 0
            log.error("write_space_weather_db_failure", source=source, error=str(exc))

    # --- Transaction 2: audit row (always attempted) ---
    ended_at = int(time.time())
    try:
        with get_write_conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT INTO poller_runs "
                "(source, started_at, ended_at, status, events_fetched, "
                "events_written, error_summary) VALUES (?,?,?,?,?,?,?)",
                (
                    source,
                    started_at,
                    ended_at,
                    events_status,
                    fetched,
                    written,
                    events_error[:200] if events_error else None,
                ),
            )
            conn.execute("COMMIT")
    except sqlite3.Error as exc:
        log.error("poller_runs_emit_failed", source=source, error=str(exc))

    return fetched, written


def write_lightning_batch(
    strikes: list[LightningStrike],
    started_at: int,
    status: str,
    error_summary: str | None = None,
) -> tuple[int, int]:
    """Batch-insert ``lightning_strikes`` + always emit one ``poller_runs`` row (POLL-05).

    Two transactions (insert first, then audit) so the poller_runs row
    survives any insert-side rollback. ``INSERT OR IGNORE`` is unnecessary
    in production (Blitzortung's volunteer feed emits each strike once and
    the schema lacks a UNIQUE constraint) but using a plain INSERT keeps
    the path simple.

    Called from ``BlitzortungClient._flush`` every
    ``settings.poller_blitzortung_flush_interval_sec`` (default 30s).
    Empty-buffer flushes still emit the audit row so /api/health and
    ``last_poll_status`` stay fresh during quiet stretches.

    Args:
        strikes: in-radius strikes accumulated since the last flush. May
            be empty (legitimate quiet window).
        started_at: this flush's started_at (unix epoch seconds).
        status: ``poller_runs.status`` — typically ``'success'`` on a
            normal flush, ``'transient_fail'`` when the WS is down.
        error_summary: short human-readable context for the audit row
            (truncated to 200 chars).

    Returns:
        ``(fetched, written)`` — both equal ``len(strikes)`` on success.
    """
    source = "blitzortung"
    fetched = len(strikes)
    written = 0
    events_status = status
    events_error = error_summary

    # --- Transaction 1: strikes insert (best-effort) ---
    if strikes:
        try:
            with get_write_conn() as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    for s in strikes:
                        cur = conn.execute(
                            "INSERT INTO lightning_strikes "
                            "(ts, latitude, longitude, distance_km) "
                            "VALUES (?,?,?,?)",
                            (s.ts, s.latitude, s.longitude, s.distance_km),
                        )
                        written += cur.rowcount
                    conn.execute("COMMIT")
                except Exception:
                    conn.execute("ROLLBACK")
                    raise
        except (sqlite3.Error, sqlite3.ProgrammingError, sqlite3.InterfaceError) as exc:
            events_status = "db_fail"
            events_error = f"{type(exc).__name__}: {exc}"
            written = 0
            log.error("write_lightning_batch_db_failure", source=source, error=str(exc))

    # --- Transaction 2: audit row (always attempted) ---
    ended_at = int(time.time())
    try:
        with get_write_conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT INTO poller_runs "
                "(source, started_at, ended_at, status, events_fetched, "
                "events_written, error_summary) VALUES (?,?,?,?,?,?,?)",
                (
                    source,
                    started_at,
                    ended_at,
                    events_status,
                    fetched,
                    written,
                    events_error[:200] if events_error else None,
                ),
            )
            conn.execute("COMMIT")
    except sqlite3.Error as exc:
        log.error("poller_runs_emit_failed", source=source, error=str(exc))

    return fetched, written


def write_forecast(
    hourly: list[ForecastHourly],
    daily: list[ForecastDaily],
    meta: dict[str, int | str] | None,
    started_at: int,
    status: str,
    error_summary: str | None = None,
) -> None:
    """Replace-on-fetch write of the cached forecast + always emit one poller_runs row.

    The forecast cache holds exactly ONE current forecast (10-RESEARCH Pattern 3):
    each poll DELETEs the prior ``forecast_hourly`` / ``forecast_daily`` rows then
    bulk-inserts the new ones, so old ``ts`` keys never linger as the horizon shifts
    each hour (DELETE+INSERT, NOT ``INSERT OR REPLACE`` keyed on ts). The single-row
    ``forecast_meta`` (id CHECK=1) is upserted as the freshness anchor.

    Two transactions (data write, then audit insert) follow the Phase 4 discipline
    so the ``poller_runs`` audit row survives any data-write rollback (Pitfall 10).
    On a failure ``status`` (empty hourly/daily, ``meta is None``) no forecast rows
    are written but the audit row is still emitted.

    Args:
        hourly: parsed hourly rows (empty on fetch/parse failure).
        daily: parsed daily rows (empty on fetch/parse failure).
        meta: parser meta dict (``utc_offset_seconds`` / ``timezone`` /
            ``fetched_at``), or ``None`` on failure.
        started_at: poll start time (unix epoch seconds).
        status: ``poller_runs.status`` — ``success`` | ``transient_fail`` |
            ``parse_fail`` | ``db_fail``.
        error_summary: short human-readable summary, truncated to 200 chars.
    """
    source = "forecast"
    fetched = len(hourly) + len(daily)
    written = 0
    events_status = status
    events_error = error_summary

    # --- Transaction 1: replace-on-fetch data write (only with data + meta) ---
    if (hourly or daily) and meta is not None:
        fetched_at = int(meta["fetched_at"])
        try:
            with get_write_conn() as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    conn.execute("DELETE FROM forecast_hourly")
                    for h in hourly:
                        conn.execute(
                            "INSERT INTO forecast_hourly "
                            "(ts, temp_c, apparent_temp_c, relative_humidity_pct, "
                            "surface_pressure_hpa, precip_prob_pct, weather_code, "
                            "wind_speed_kmh, fetched_at) VALUES (?,?,?,?,?,?,?,?,?)",
                            (
                                h.ts,
                                h.temp_c,
                                h.apparent_temp_c,
                                h.relative_humidity_pct,
                                h.surface_pressure_hpa,
                                h.precip_prob_pct,
                                h.weather_code,
                                h.wind_speed_kmh,
                                fetched_at,
                            ),
                        )
                        written += 1
                    conn.execute("DELETE FROM forecast_daily")
                    for d in daily:
                        conn.execute(
                            "INSERT INTO forecast_daily "
                            "(ts, temp_max_c, temp_min_c, precip_prob_max_pct, "
                            "weather_code, wind_speed_max_kmh, fetched_at) "
                            "VALUES (?,?,?,?,?,?,?)",
                            (
                                d.ts,
                                d.temp_max_c,
                                d.temp_min_c,
                                d.precip_prob_max_pct,
                                d.weather_code,
                                d.wind_speed_max_kmh,
                                fetched_at,
                            ),
                        )
                        written += 1
                    conn.execute(
                        "INSERT OR REPLACE INTO forecast_meta "
                        "(id, fetched_at, utc_offset_seconds, timezone) VALUES (1, ?, ?, ?)",
                        (fetched_at, int(meta["utc_offset_seconds"]), str(meta["timezone"])),
                    )
                    conn.execute("COMMIT")
                except Exception:
                    conn.execute("ROLLBACK")
                    raise
        except (sqlite3.Error, sqlite3.ProgrammingError, sqlite3.InterfaceError) as exc:
            events_status = "db_fail"
            events_error = f"{type(exc).__name__}: {exc}"
            written = 0
            log.error("forecast_write_db_failure", source=source, error=str(exc))

    # --- Transaction 2: audit row (always attempted) ---
    ended_at = int(time.time())
    try:
        with get_write_conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT INTO poller_runs "
                "(source, started_at, ended_at, status, events_fetched, "
                "events_written, error_summary) VALUES (?,?,?,?,?,?,?)",
                (
                    source,
                    started_at,
                    ended_at,
                    events_status,
                    fetched,
                    written,
                    events_error[:200] if events_error else None,
                ),
            )
            conn.execute("COMMIT")
    except sqlite3.Error as exc:
        log.error("poller_runs_emit_failed", source=source, error=str(exc))


def write_air_quality(
    snapshot: AirQualitySnapshot | None,
    meta: dict[str, int | str] | None,
    started_at: int,
    status: str,
    error_summary: str | None = None,
) -> None:
    """Replace-on-fetch write of the cached AQ snapshot + always emit one poller_runs row.

    The air-quality cache holds exactly ONE current snapshot (migration 0006
    ``air_quality`` id=1): each successful poll ``INSERT OR REPLACE``s id=1 so
    growth is bounded at one row as the reading refreshes hourly. The single-row
    ``air_quality_meta`` (id CHECK=1) is upserted as the freshness anchor.

    Two transactions (data write, then audit insert) follow the Phase 4 discipline
    so the ``poller_runs`` audit row survives any data-write rollback (Pitfall 10).
    On a failure ``status`` (``snapshot``/``meta`` None) no air_quality row is
    written but the audit row is still emitted.

    Args:
        snapshot: parsed snapshot, or ``None`` on fetch/parse failure.
        meta: parser meta dict (``utc_offset_seconds`` / ``timezone`` /
            ``fetched_at``), or ``None`` on failure.
        started_at: poll start time (unix epoch seconds).
        status: ``poller_runs.status`` — ``success`` | ``transient_fail`` |
            ``parse_fail`` | ``db_fail``.
        error_summary: short human-readable summary, truncated to 200 chars.
    """
    source = "air_quality"
    fetched = 1 if snapshot is not None else 0
    written = 0
    events_status = status
    events_error = error_summary

    # --- Transaction 1: replace-on-fetch data write (only with snapshot + meta) ---
    if snapshot is not None and meta is not None:
        fetched_at = int(meta["fetched_at"])
        try:
            with get_write_conn() as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    conn.execute(
                        "INSERT OR REPLACE INTO air_quality "
                        "(id, ts, european_aqi, pm2_5, pm10, nitrogen_dioxide, ozone, "
                        "sulphur_dioxide, uv_index, alder_pollen, birch_pollen, grass_pollen, "
                        "mugwort_pollen, olive_pollen, ragweed_pollen, fetched_at) "
                        "VALUES (1, ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            snapshot.ts,
                            snapshot.european_aqi,
                            snapshot.pm2_5,
                            snapshot.pm10,
                            snapshot.nitrogen_dioxide,
                            snapshot.ozone,
                            snapshot.sulphur_dioxide,
                            snapshot.uv_index,
                            snapshot.alder_pollen,
                            snapshot.birch_pollen,
                            snapshot.grass_pollen,
                            snapshot.mugwort_pollen,
                            snapshot.olive_pollen,
                            snapshot.ragweed_pollen,
                            fetched_at,
                        ),
                    )
                    conn.execute(
                        "INSERT OR REPLACE INTO air_quality_meta "
                        "(id, fetched_at, utc_offset_seconds, timezone) VALUES (1, ?, ?, ?)",
                        (fetched_at, int(meta["utc_offset_seconds"]), str(meta["timezone"])),
                    )
                    written = 1
                    conn.execute("COMMIT")
                except Exception:
                    conn.execute("ROLLBACK")
                    raise
        except (sqlite3.Error, sqlite3.ProgrammingError, sqlite3.InterfaceError) as exc:
            events_status = "db_fail"
            events_error = f"{type(exc).__name__}: {exc}"
            written = 0
            log.error("air_quality_write_db_failure", source=source, error=str(exc))

    # --- Transaction 2: audit row (always attempted) ---
    ended_at = int(time.time())
    try:
        with get_write_conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT INTO poller_runs "
                "(source, started_at, ended_at, status, events_fetched, "
                "events_written, error_summary) VALUES (?,?,?,?,?,?,?)",
                (
                    source,
                    started_at,
                    ended_at,
                    events_status,
                    fetched,
                    written,
                    events_error[:200] if events_error else None,
                ),
            )
            conn.execute("COMMIT")
    except sqlite3.Error as exc:
        log.error("poller_runs_emit_failed", source=source, error=str(exc))


def write_aurora_status(
    snapshot: AuroraSnapshot | None,
    started_at: int,
    status: str,
    error_summary: str | None = None,
) -> tuple[int, int]:
    """Write 0 or 1 aurora_status row + always emit one poller_runs row (POLL-06).

    No dedup — state-machine transitions matter (a green->amber that we
    skipped would be a regression in the dashboard story). The writer simply
    inserts whatever the parser produced.

    Two transactions (events first, then audit) follow the Phase 4 discipline
    so the poller_runs audit row survives any event-write rollback.

    Args:
        snapshot: parsed status, or ``None`` when fetch/parse failed (in
            which case ``status`` is ``transient_fail`` or ``parse_fail``
            and no aurora_status row is written, only the audit row).
        started_at: unix epoch seconds at poll start (for poller_runs).
        status: poller_runs.status value
            (``success`` | ``transient_fail`` | ``parse_fail`` | ``db_fail``).
        error_summary: short human-readable error context for the audit
            row, truncated to 200 chars at write time.

    Returns:
        ``(fetched, written)`` — both 0 or 1 for aurora.
    """
    source = "aurora"
    fetched = 1 if snapshot is not None else 0
    written = 0
    events_status = status
    events_error = error_summary

    # --- Transaction 1: aurora_status insert (only when we have a snapshot) ---
    if snapshot is not None:
        try:
            with get_write_conn() as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    conn.execute(
                        "INSERT INTO aurora_status (ts, status, detail) VALUES (?,?,?)",
                        (snapshot.ts, snapshot.status, snapshot.detail),
                    )
                    written = 1
                    conn.execute("COMMIT")
                except Exception:
                    conn.execute("ROLLBACK")
                    raise
        except (sqlite3.Error, sqlite3.ProgrammingError, sqlite3.InterfaceError) as exc:
            events_status = "db_fail"
            events_error = f"{type(exc).__name__}: {exc}"
            written = 0
            log.error("write_aurora_status_db_failure", source=source, error=str(exc))

    # --- Transaction 2: audit row (always attempted) ---
    ended_at = int(time.time())
    try:
        with get_write_conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT INTO poller_runs "
                "(source, started_at, ended_at, status, events_fetched, "
                "events_written, error_summary) VALUES (?,?,?,?,?,?,?)",
                (
                    source,
                    started_at,
                    ended_at,
                    events_status,
                    fetched,
                    written,
                    events_error[:200] if events_error else None,
                ),
            )
            conn.execute("COMMIT")
    except sqlite3.Error as exc:
        log.error("poller_runs_emit_failed", source=source, error=str(exc))

    return fetched, written


def write_nmdb(
    counts: list[NmdbCount] | None,
    meta: dict[str, int | str] | None,
    started_at: int,
    status: str,
    error_summary: str | None = None,
) -> None:
    """Append-window write of NMDB counts + always emit one poller_runs row.

    NMDB counts are an APPEND window (migration 0007 ``nmdb_counts``): each poll
    fetches an overlapping ~8-day window, so rows are ``INSERT OR IGNORE`` on
    ``UNIQUE(station, ts)`` — a re-fetch of overlapping intervals does not
    duplicate. The single-row ``nmdb_meta`` (id CHECK=1) is upserted as the
    ``/api/health`` freshness anchor (``fetched_at``, NOT MAX(ts) — Pitfall 2).

    Two transactions (data write, then audit insert) follow the Phase 4 discipline
    so the ``poller_runs`` audit row survives any data-write rollback (Pitfall 10).
    On a failure ``status`` (``counts``/``meta`` None) no rows are written but the
    audit row is still emitted.

    Args:
        counts: parsed NMDB counts, or ``None`` on fetch/parse failure.
        meta: parser meta dict (``fetched_at`` / ``station``), or ``None`` on
            failure. ``failures`` (if present) is ignored here — the threshold is
            decided in ``__main__`` before the write.
        started_at: poll start time (unix epoch seconds).
        status: ``poller_runs.status`` — ``success`` | ``transient_fail`` |
            ``parse_fail`` | ``db_fail``.
        error_summary: short human-readable summary, truncated to 200 chars.
    """
    source = "nmdb"
    fetched = len(counts) if counts is not None else 0
    written = 0
    events_status = status
    events_error = error_summary

    # --- Transaction 1: append-window data write (only with counts + meta) ---
    if counts is not None and meta is not None:
        fetched_at = int(meta["fetched_at"])
        nmdb_station = str(meta["station"])
        try:
            with get_write_conn() as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    for c in counts:
                        conn.execute(
                            "INSERT OR IGNORE INTO nmdb_counts "
                            "(station, ts, counts_per_sec) VALUES (?,?,?)",
                            (c.station, c.ts, c.counts_per_sec),
                        )
                    conn.execute(
                        "INSERT OR REPLACE INTO nmdb_meta (id, fetched_at, station) "
                        "VALUES (1, ?, ?)",
                        (fetched_at, nmdb_station),
                    )
                    written = len(counts)
                    conn.execute("COMMIT")
                except Exception:
                    conn.execute("ROLLBACK")
                    raise
        except (sqlite3.Error, sqlite3.ProgrammingError, sqlite3.InterfaceError) as exc:
            events_status = "db_fail"
            events_error = f"{type(exc).__name__}: {exc}"
            written = 0
            log.error("nmdb_write_db_failure", source=source, error=str(exc))

    # --- Transaction 2: audit row (always attempted) ---
    ended_at = int(time.time())
    try:
        with get_write_conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT INTO poller_runs "
                "(source, started_at, ended_at, status, events_fetched, "
                "events_written, error_summary) VALUES (?,?,?,?,?,?,?)",
                (
                    source,
                    started_at,
                    ended_at,
                    events_status,
                    fetched,
                    written,
                    events_error[:200] if events_error else None,
                ),
            )
            conn.execute("COMMIT")
    except sqlite3.Error as exc:
        log.error("poller_runs_emit_failed", source=source, error=str(exc))
