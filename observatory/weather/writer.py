"""SQLite writer for weather readings (Phase 3-02).

Single source of truth for INSERT into the ``weather`` table. Uses
``BEGIN IMMEDIATE`` per the project's write discipline (DATA-02) and
``INSERT OR IGNORE`` to dedupe replayed retained MQTT messages — relies
on the UNIQUE(node_id, ts) index added in migration 0003.

DB errors are caught, logged at ERROR (event=weather_write_error), and
the function returns ``False``. The subscriber (03-03) is expected to
log + drop and continue — firmware's local upload cache is the
durability backstop, not in-process retry.

Rowcount semantics:
    - ``True``  : cursor.rowcount == 1 (a new row was inserted)
    - ``False`` : cursor.rowcount == 0 (UNIQUE collision — dedup) OR
                  any sqlite3 error OR bad timestamp parse
"""

from __future__ import annotations

import sqlite3

import structlog

from observatory.db.connection import get_write_conn
from observatory.pollers._parse_ts import parse_ts
from observatory.weather.payload import WeatherEnvelope

log = structlog.get_logger(__name__)


def write_reading(envelope: WeatherEnvelope, db_path: str | None = None) -> bool:
    """Persist one parsed Pimoroni envelope into the ``weather`` table.

    Args:
        envelope: parsed payload from ``observatory.weather.payload.parse_envelope``.
        db_path: SQLite file path override (primarily for tests/tooling).
            ``None`` falls through to ``observatory.config.settings.observatory_db_path``.

    Returns:
        ``True`` if a new row was inserted (cursor.rowcount == 1).
        ``False`` on dedup (UNIQUE(node_id, ts) collision), bad timestamp,
        or any sqlite3 error. Never raises — DB errors are swallowed so
        the MQTT subscriber loop stays alive across transient faults.
    """
    try:
        ts = parse_ts(envelope.timestamp)
    except Exception as exc:
        log.error(
            "weather_write_error",
            error="bad_timestamp",
            timestamp=envelope.timestamp,
            node_id=envelope.nickname,
            exc_info=exc,
        )
        return False

    try:
        with get_write_conn(db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                cursor = conn.execute(
                    "INSERT OR IGNORE INTO weather "
                    "(node_id, ts, temp_c, humidity_pct, pressure_hpa, "
                    "lux, battery_v, wifi_rssi) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        envelope.nickname,
                        ts,
                        envelope.readings.temp_c,
                        envelope.readings.humidity_pct,
                        envelope.readings.pressure_hpa,
                        envelope.readings.lux,
                        # battery_v / wifi_rssi are NULL on every row by design:
                        # the Enviro Weather board (AA-powered, stock firmware)
                        # never publishes voltage or RSSI over MQTT, so these
                        # columns stay empty. Confirmed with the operator — this
                        # is expected, not a missing-mapping bug. (The voltage
                        # alias below would persist it if firmware ever sent it.)
                        envelope.readings.battery_v,  # None unless firmware sends `voltage`
                        None,  # wifi_rssi — firmware never publishes it
                    ),
                )
                inserted = cursor.rowcount == 1
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
    except sqlite3.Error as exc:
        log.error(
            "weather_write_error",
            error=str(exc),
            error_type=type(exc).__name__,
            node_id=envelope.nickname,
            ts=ts,
        )
        return False

    if inserted:
        log.info("weather_row_written", node_id=envelope.nickname, ts=ts)
    else:
        log.info("weather_row_deduped", node_id=envelope.nickname, ts=ts)
    return inserted
