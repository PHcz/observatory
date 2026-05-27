"""Test scripts/check-weather-gaps.py against synthetic weather rows."""

from __future__ import annotations

import importlib.util
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check-weather-gaps.py"
MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
SCHEMA_0001 = MIGRATIONS_DIR / "0001_initial_schema.sql"


def _load():
    spec = importlib.util.spec_from_file_location("check_gaps", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """Tmp SQLite DB with weather schema (migration 0001) applied."""
    db_path = tmp_path / "test_observatory.db"
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.executescript(SCHEMA_0001.read_text())
    conn.close()
    return db_path


def _seed(db_path: Path, ts_list: list[int]) -> None:
    conn = sqlite3.connect(str(db_path))
    for ts in ts_list:
        conn.execute(
            "INSERT INTO weather (node_id, ts, temp_c) VALUES ('observatory-weather', ?, 20.0)",
            (ts,),
        )
    conn.commit()
    conn.close()


def test_empty_table_fails(tmp_db: Path) -> None:
    mod = _load()
    since = int(time.time()) - 48 * 3600
    r = mod.analyze_gaps(str(tmp_db), since, 4500)
    assert r["pass"] is False
    assert r["row_count"] == 0


def test_dense_rows_pass(tmp_db: Path) -> None:
    mod = _load()
    now = int(time.time())
    # 49 rows every 25min = 48h coverage
    _seed(tmp_db, [now - i * 1500 for i in range(49)])
    since = now - 48 * 3600 - 600
    r = mod.analyze_gaps(str(tmp_db), since, 4500)
    assert r["pass"] is True
    assert r["max_gap_sec"] == 1500


def test_big_gap_fails(tmp_db: Path) -> None:
    mod = _load()
    now = int(time.time())
    # insert ts at now and now - 2hr (7200s gap) — exceeds 4500s threshold
    _seed(tmp_db, [now - 7200, now])
    since = now - 48 * 3600
    r = mod.analyze_gaps(str(tmp_db), since, 4500)
    assert r["pass"] is False
    assert r["max_gap_sec"] == 7200


def test_help_runs() -> None:
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert r.returncode == 0
    assert "--threshold-sec" in r.stdout
    assert "--since-hours" in r.stdout
