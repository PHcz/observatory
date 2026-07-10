"""SQLite writer for coalesced indoor-air readings (Phase 14 INDOOR-02).

Single source of truth for INSERT into ``indoor_air``. Mirrors the weather
writer's discipline: ``BEGIN IMMEDIATE`` (DATA-02), ``INSERT OR IGNORE`` to
dedup on UNIQUE(node_id, ts), all errors swallowed + logged so the MQTT
subscriber loop stays alive.

``values`` is keyed by indoor_air *column names* (temp_c, humidity_pct,
pressure_hpa, co2_ppm, gas_index, lux, battery_v, wifi_rssi) — the closed set
produced by ``observatory.indoor.topic.METRIC_COLUMNS``. Any column absent
from the dict is written NULL. Column names are never taken from the payload,
so the SQL is fully static (no injection surface).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping

import structlog

from observatory.db.connection import get_write_conn

log = structlog.get_logger(__name__)


def write_reading(
    node_id: str,
    ts: int,
    values: Mapping[str, float | int],
    db_path: str | None = None,
) -> bool:
    """Persist one coalesced indoor reading. Returns True on a new row.

    Args:
        node_id: room label (topic segment), e.g. "living-room".
        ts: Unix epoch seconds (server receive time).
        values: column-name → value for the metrics present this cycle.
        db_path: SQLite path override (tests/tooling); None → settings default.

    Returns:
        True if a new row was inserted; False on UNIQUE(node_id, ts) dedup or
        any sqlite3 error. Never raises.
    """
    try:
        with get_write_conn(db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                cursor = conn.execute(
                    "INSERT OR IGNORE INTO indoor_air "
                    "(node_id, ts, temp_c, humidity_pct, pressure_hpa, co2_ppm, "
                    "gas_index, lux, battery_v, wifi_rssi) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        node_id,
                        ts,
                        values.get("temp_c"),
                        values.get("humidity_pct"),
                        values.get("pressure_hpa"),
                        values.get("co2_ppm"),
                        values.get("gas_index"),
                        values.get("lux"),
                        values.get("battery_v"),
                        values.get("wifi_rssi"),
                    ),
                )
                inserted = cursor.rowcount == 1
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
    except sqlite3.Error as exc:
        log.error(
            "indoor_write_error",
            error=str(exc),
            error_type=type(exc).__name__,
            node_id=node_id,
            ts=ts,
        )
        return False

    if inserted:
        log.info("indoor_row_written", node_id=node_id, ts=ts, metrics=sorted(values))
    else:
        log.info("indoor_row_deduped", node_id=node_id, ts=ts)
    return inserted
