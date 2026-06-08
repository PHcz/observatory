"""Phase 16: verify that migrations 0008 (alerts) and 0009 (muon_weekly_summary)
apply cleanly to a fresh database.

This test MUST PASS NOW — the migrations exist (Task 1). It gates Wave 0
acceptance and verifies the schema contract for all downstream tasks.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from observatory.db.migrations import apply_migrations


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


def test_phase16_migrations_apply(tmp_db_path: Path) -> None:
    """Apply all migrations to a fresh DB; assert Phase 16 tables are present."""
    apply_migrations(str(tmp_db_path))
    tables = _tables(tmp_db_path)
    assert "alerts" in tables, f"'alerts' table missing after migrations; found: {tables}"
    assert "muon_weekly_summary" in tables, (
        f"'muon_weekly_summary' table missing after migrations; found: {tables}"
    )


def test_phase16_alerts_indexes(tmp_db_path: Path) -> None:
    """Verify Phase 16 alert indexes are created."""
    apply_migrations(str(tmp_db_path))
    indexes = _indexes(tmp_db_path)
    assert "idx_alerts_active" in indexes, f"'idx_alerts_active' index missing; found: {indexes}"
    assert "idx_alerts_ts" in indexes, f"'idx_alerts_ts' index missing; found: {indexes}"


def test_phase16_muon_weekly_summary_index(tmp_db_path: Path) -> None:
    """Verify Phase 16 muon_weekly_summary index is created."""
    apply_migrations(str(tmp_db_path))
    indexes = _indexes(tmp_db_path)
    assert "idx_muon_weekly_ts" in indexes, f"'idx_muon_weekly_ts' index missing; found: {indexes}"
