"""Phase 14 INDOOR-02: indoor_air writer — INSERT, NULLs, dedup."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from observatory.indoor.writer import write_reading

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "migrations" / "0010_indoor_air.sql"


def _make_db(tmp_path: Path) -> str:
    db = tmp_path / "test.db"
    conn = sqlite3.connect(db)
    conn.executescript(MIGRATION.read_text())
    conn.commit()
    conn.close()
    return str(db)


def test_write_full_reading(tmp_path: Path) -> None:
    db = _make_db(tmp_path)
    ok = write_reading(
        "living-room",
        1_700_000_000,
        {"co2_ppm": 822, "temp_c": 21.4, "humidity_pct": 39.2, "pressure_hpa": 1017.1},
        db,
    )
    assert ok is True
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT node_id, ts, temp_c, humidity_pct, pressure_hpa, co2_ppm, gas_index, lux "
        "FROM indoor_air"
    ).fetchone()
    conn.close()
    assert row == ("living-room", 1_700_000_000, 21.4, 39.2, 1017.1, 822, None, None)


def test_partial_reading_leaves_missing_columns_null(tmp_path: Path) -> None:
    db = _make_db(tmp_path)
    assert write_reading("bedroom", 1_700_000_100, {"co2_ppm": 640}, db) is True
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT co2_ppm, temp_c, pressure_hpa FROM indoor_air WHERE node_id='bedroom'"
    ).fetchone()
    conn.close()
    assert row == (640, None, None)


def test_dedup_on_node_and_ts(tmp_path: Path) -> None:
    db = _make_db(tmp_path)
    assert write_reading("living-room", 1_700_000_000, {"co2_ppm": 800}, db) is True
    # same (node_id, ts) → UNIQUE collision → not inserted again
    assert write_reading("living-room", 1_700_000_000, {"co2_ppm": 810}, db) is False
    conn = sqlite3.connect(db)
    count = conn.execute("SELECT COUNT(*) FROM indoor_air").fetchone()[0]
    conn.close()
    assert count == 1


def test_bad_db_path_returns_false_not_raises(tmp_path: Path) -> None:
    # Missing table → sqlite3 error → swallowed, returns False.
    empty = tmp_path / "empty.db"
    sqlite3.connect(empty).close()
    assert write_reading("x", 1, {"co2_ppm": 500}, str(empty)) is False
