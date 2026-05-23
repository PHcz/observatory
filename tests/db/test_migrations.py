"""DATA-01 + DATA-03: schema migrations apply all 6 tables, all 7 indexes; idempotent."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from observatory.db.migrations import apply_migrations

EXPECTED_TABLES = {
    "weather",
    "muon_events",
    "earthquakes",
    "space_weather",
    "lightning_strikes",
    "aurora_status",
}

EXPECTED_INDEXES = {
    "idx_weather_ts",
    "idx_muon_ts",
    "idx_quakes_ts",
    "idx_quakes_mag",
    "idx_sw_ts",
    "idx_lightning_ts",
    "idx_aurora_ts",
}


def _tables(db_path: Path) -> set[str]:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "AND name NOT LIKE '_yoyo_%'"
        ).fetchall()
        return {r[0] for r in rows}
    finally:
        conn.close()


def _indexes(db_path: Path) -> set[str]:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        return {r[0] for r in rows}
    finally:
        conn.close()


def test_apply_migrations_creates_all_tables(tmp_db_path: Path) -> None:
    apply_migrations(str(tmp_db_path))
    assert _tables(tmp_db_path) >= EXPECTED_TABLES


def test_apply_migrations_creates_all_indexes(tmp_db_path: Path) -> None:
    apply_migrations(str(tmp_db_path))
    assert _indexes(tmp_db_path) >= EXPECTED_INDEXES


def test_apply_migrations_idempotent(tmp_db_path: Path) -> None:
    first = apply_migrations(str(tmp_db_path))
    second = apply_migrations(str(tmp_db_path))
    assert first >= 1, "first run should apply at least one migration"
    assert second == 0, f"second run should be a no-op, applied {second}"


def test_earthquakes_unique_source_external_id(tmp_db_path: Path) -> None:
    apply_migrations(str(tmp_db_path))
    conn = sqlite3.connect(str(tmp_db_path))
    try:
        conn.execute(
            "INSERT INTO earthquakes (source, external_id, ts) VALUES ('usgs', 'us7000abcd', 1)"
        )
        conn.commit()
        try:
            conn.execute(
                "INSERT INTO earthquakes (source, external_id, ts) VALUES ('usgs', 'us7000abcd', 2)"
            )
            conn.commit()
            raise AssertionError("expected UNIQUE constraint violation")
        except sqlite3.IntegrityError:
            pass
    finally:
        conn.close()
