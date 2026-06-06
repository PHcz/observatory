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
    "air_quality",
    "air_quality_meta",
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


REPO_MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"


class TestMigration0004IsLocal:
    """Phase 8.5 UI-18: migration 0004 adds is_local column + backfills BGS rows."""

    def test_column_added_with_correct_shape(self, tmp_db_path: Path) -> None:
        apply_migrations(str(tmp_db_path))
        conn = sqlite3.connect(str(tmp_db_path))
        try:
            cols = {
                r[1]: (r[2], r[3], r[4])
                for r in conn.execute("PRAGMA table_info(earthquakes)").fetchall()
            }
        finally:
            conn.close()
        assert "is_local" in cols, "earthquakes.is_local column missing after migrations"
        type_str, notnull, dflt = cols["is_local"]
        assert type_str == "INTEGER"
        assert notnull == 1, "is_local must be NOT NULL"
        # SQLite stores DEFAULT value as a string literal in PRAGMA output.
        assert str(dflt) == "0", f"is_local default must be 0, got {dflt!r}"

    def _apply_through_0003(self, db_path: Path, tmp_path: Path) -> None:
        """Apply migrations 0001..0003 via yoyo (skip 0004) so we can seed pre-state.

        Copies only the first three .sql files into a tmp migrations dir, runs
        yoyo against that, so yoyo's tracking tables are correctly populated
        and a subsequent ``apply_migrations(db_path)`` against the real
        migrations dir only applies 0004.
        """
        sub = tmp_path / "migrations_pre0004"
        sub.mkdir()
        for sql_file in sorted(REPO_MIGRATIONS.glob("0001_*.sql")):
            (sub / sql_file.name).write_text(sql_file.read_text())
        for sql_file in sorted(REPO_MIGRATIONS.glob("0002_*.sql")):
            (sub / sql_file.name).write_text(sql_file.read_text())
        for sql_file in sorted(REPO_MIGRATIONS.glob("0003_*.sql")):
            (sub / sql_file.name).write_text(sql_file.read_text())
        apply_migrations(str(db_path), migrations_dir=str(sub))

    def test_backfill_sets_is_local_for_bgs_rows(self, tmp_db_path: Path, tmp_path: Path) -> None:
        """Pre-0004 BGS row gets is_local=1 after migration runs."""
        self._apply_through_0003(tmp_db_path, tmp_path)
        conn = sqlite3.connect(str(tmp_db_path), isolation_level=None)
        try:
            conn.execute(
                "INSERT INTO earthquakes (source, external_id, ts, magnitude, "
                "depth_km, latitude, longitude, place) "
                "VALUES ('bgs', 'bgs_backfill_1', 1700000000, 2.5, 5.0, 53.0, -1.5, 'UK')",
            )
        finally:
            conn.close()
        # Now apply 0004 via yoyo (apply_migrations skips already-applied 0001-0003)
        applied = apply_migrations(str(tmp_db_path))
        assert applied >= 1, "0004 migration should apply"
        conn = sqlite3.connect(str(tmp_db_path))
        try:
            row = conn.execute(
                "SELECT is_local FROM earthquakes WHERE external_id = 'bgs_backfill_1'"
            ).fetchone()
        finally:
            conn.close()
        assert row is not None
        assert row[0] == 1, f"BGS row should be backfilled is_local=1, got {row[0]}"

    def test_backfill_does_not_touch_non_bgs_rows(self, tmp_db_path: Path, tmp_path: Path) -> None:
        """Pre-0004 USGS row stays is_local=0 after migration (Pitfall 8)."""
        self._apply_through_0003(tmp_db_path, tmp_path)
        conn = sqlite3.connect(str(tmp_db_path), isolation_level=None)
        try:
            conn.execute(
                "INSERT INTO earthquakes (source, external_id, ts, magnitude, "
                "depth_km, latitude, longitude, place) "
                "VALUES ('usgs', 'usgs_backfill_1', 1700000000, 4.5, 10.0, 0.0, 0.0, 'X')",
            )
        finally:
            conn.close()
        apply_migrations(str(tmp_db_path))
        conn = sqlite3.connect(str(tmp_db_path))
        try:
            row = conn.execute(
                "SELECT is_local FROM earthquakes WHERE external_id = 'usgs_backfill_1'"
            ).fetchone()
        finally:
            conn.close()
        assert row is not None
        assert row[0] == 0, f"USGS pre-existing row stays is_local=0, got {row[0]}"


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
