"""Phase 6 — tests for db_watcher. Implemented by Plan 06-06."""

from __future__ import annotations

import asyncio
import sqlite3
import time
from pathlib import Path

import pytest

import observatory.config as _config_mod
from observatory.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_0001 = REPO_ROOT / "migrations" / "0001_initial_schema.sql"
SCHEMA_0002 = REPO_ROOT / "migrations" / "0002_poller_runs.sql"


@pytest.fixture
def seeded_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a seeded SQLite DB with known rows for testing db_watcher."""
    db_path = tmp_path / "watcher_test.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA_0001.read_text())
    conn.executescript(SCHEMA_0002.read_text())
    conn.execute("PRAGMA journal_mode=WAL")

    now = int(time.time())

    # Seed: 10 weather rows, 5 muon, 3 earthquakes (old data — should NOT be replayed)
    for i in range(10):
        conn.execute(
            "INSERT INTO weather (node_id, ts, temp_c) VALUES (?, ?, ?)",
            ("node1", now - 3600 + i * 10, 15.0 + i * 0.1),
        )
    for i in range(5):
        conn.execute(
            "INSERT INTO muon_events (ts, amplitude, coincidence) VALUES (?, ?, ?)",
            (now - 1800 + i * 60, 0.5, 0),
        )
    for i in range(3):
        conn.execute(
            "INSERT INTO earthquakes (source, external_id, ts, magnitude) VALUES (?, ?, ?, ?)",
            ("usgs", f"eq-{i}", now - 7200 + i * 100, 3.5 + i * 0.1),
        )
    conn.commit()
    conn.close()

    monkeypatch.setenv("OBSERVATORY_DB_PATH", str(db_path))
    monkeypatch.setenv("HOME_LAT", "51.5074")
    monkeypatch.setenv("HOME_LON", "-0.1278")
    s = Settings()
    monkeypatch.setattr(_config_mod, "settings", s)

    # Also patch settings on the db_watcher module (uses from-import at module level)
    import observatory.api.db_watcher as _dw_mod

    monkeypatch.setattr(_dw_mod, "settings", s, raising=False)

    return db_path


# ---------------------------------------------------------------------------
# T1: bootstrap — old rows do NOT trigger fanout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_db_watcher_bootstrap_skips_old_rows(
    seeded_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bootstrap: last_seen on startup matches MAX(ts); old rows not fanned out."""
    s = _config_mod.settings
    monkeypatch.setattr(s, "api_db_watcher_interval_sec", 0.05, raising=False)

    received: list[dict] = []  # type: ignore[type-arg]

    async def fake_fanout(env: dict) -> None:  # type: ignore[type-arg]
        received.append(env)

    monkeypatch.setattr("observatory.api.db_watcher.fanout_event", fake_fanout)

    from observatory.api.db_watcher import db_watcher_loop

    task = asyncio.create_task(db_watcher_loop())
    await asyncio.sleep(0.15)  # time for bootstrap + one tick
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # No old rows should have been fanned out
    assert received == [], f"Expected no fanout of old rows, got: {received}"


# ---------------------------------------------------------------------------
# T2: new row after bootstrap → fanned out
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_db_watcher_fans_out_new_rows(
    seeded_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After bootstrap, insert new row → within one tick, fanout called with envelope."""
    s = _config_mod.settings
    monkeypatch.setattr(s, "api_db_watcher_interval_sec", 0.05, raising=False)

    received: list[dict] = []  # type: ignore[type-arg]

    async def fake_fanout(env: dict) -> None:  # type: ignore[type-arg]
        received.append(env)

    monkeypatch.setattr("observatory.api.db_watcher.fanout_event", fake_fanout)

    from observatory.api.db_watcher import db_watcher_loop

    task = asyncio.create_task(db_watcher_loop())
    await asyncio.sleep(0.08)  # allow bootstrap to settle

    # Insert a new weather row after bootstrap
    new_ts = int(time.time()) + 1
    conn = sqlite3.connect(str(seeded_db))
    conn.execute(
        "INSERT INTO weather (node_id, ts, temp_c) VALUES (?, ?, ?)",
        ("node1", new_ts, 22.0),
    )
    conn.commit()
    conn.close()

    await asyncio.sleep(0.15)  # allow at least one tick
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    weather_events = [e for e in received if e["type"] == "weather"]
    assert len(weather_events) >= 1, f"Expected weather fanout, got: {received}"
    assert weather_events[0]["data"]["ts"] == new_ts or weather_events[0]["ts"] == new_ts


# ---------------------------------------------------------------------------
# T3: multiple tables — 1 row per table → 6 fanouts in one tick
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_db_watcher_fans_out_multiple_tables(
    seeded_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Insert 1 row per table → 6 envelope types fanned in one tick."""
    s = _config_mod.settings
    monkeypatch.setattr(s, "api_db_watcher_interval_sec", 0.05, raising=False)

    received: list[dict] = []  # type: ignore[type-arg]

    async def fake_fanout(env: dict) -> None:  # type: ignore[type-arg]
        received.append(env)

    monkeypatch.setattr("observatory.api.db_watcher.fanout_event", fake_fanout)

    from observatory.api.db_watcher import db_watcher_loop

    task = asyncio.create_task(db_watcher_loop())
    await asyncio.sleep(0.08)  # bootstrap

    # Insert one fresh row per table
    now = int(time.time()) + 100
    conn = sqlite3.connect(str(seeded_db))
    conn.execute("INSERT INTO weather (node_id, ts, temp_c) VALUES ('n1', ?, 20.0)", (now,))
    conn.execute(
        "INSERT INTO muon_events (ts, amplitude, coincidence) VALUES (?, 0.5, 0)",
        (now,),
    )
    conn.execute(
        "INSERT INTO earthquakes (source, external_id, ts, magnitude)"
        " VALUES ('usgs','new-1',?,3.0)",
        (now,),
    )
    conn.execute(
        "INSERT INTO space_weather (ts, kp_index) VALUES (?, 3.0)",
        (now,),
    )
    conn.execute(
        "INSERT INTO lightning_strikes (ts, latitude, longitude, distance_km)"
        " VALUES (?,51.5,-0.1,100.0)",
        (now,),
    )
    conn.execute(
        "INSERT INTO aurora_status (ts, status) VALUES (?, 'green')",
        (now,),
    )
    conn.commit()
    conn.close()

    await asyncio.sleep(0.2)  # allow at least one tick
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    types_received = {e["type"] for e in received}
    expected_types = {"weather", "muon", "earthquake", "space_weather", "lightning", "aurora"}
    assert types_received == expected_types, f"Expected all 6 event types, got: {types_received}"


# ---------------------------------------------------------------------------
# T4: cancellation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_db_watcher_cancels_cleanly(seeded_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """task.cancel() → loop exits cleanly without errors."""
    s = _config_mod.settings
    monkeypatch.setattr(s, "api_db_watcher_interval_sec", 0.05, raising=False)

    async def fake_fanout(env: dict) -> None:  # type: ignore[type-arg]
        pass

    monkeypatch.setattr("observatory.api.db_watcher.fanout_event", fake_fanout)

    from observatory.api.db_watcher import db_watcher_loop

    task = asyncio.create_task(db_watcher_loop())
    await asyncio.sleep(0.1)
    task.cancel()
    # Should raise CancelledError (re-raised from loop)
    with pytest.raises(asyncio.CancelledError):
        await task


# ---------------------------------------------------------------------------
# T5: per-tick limit of 100 rows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_db_watcher_per_tick_limit(seeded_db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Insert 200 rows between ticks → first tick emits 100, next tick emits remaining 100.

    Uses 0.2s interval so ticks are cleanly separated.
    """
    s = _config_mod.settings
    # Larger interval: 0.2s so we can precisely capture per-tick counts
    monkeypatch.setattr(s, "api_db_watcher_interval_sec", 0.2, raising=False)

    received: list[dict] = []  # type: ignore[type-arg]

    async def fake_fanout(env: dict) -> None:  # type: ignore[type-arg]
        received.append(env)

    monkeypatch.setattr("observatory.api.db_watcher.fanout_event", fake_fanout)

    from observatory.api.db_watcher import db_watcher_loop

    task = asyncio.create_task(db_watcher_loop())
    await asyncio.sleep(0.05)  # wait for bootstrap SQL query to complete

    # Insert 200 weather rows with future timestamps
    now = int(time.time()) + 10
    conn = sqlite3.connect(str(seeded_db))
    for i in range(200):
        conn.execute(
            "INSERT INTO weather (node_id, ts, temp_c) VALUES ('n1', ?, 20.0)",
            (now + i,),
        )
    conn.commit()
    conn.close()

    # Wait for exactly one tick (0.2s interval; 0.25s gives a generous margin)
    await asyncio.sleep(0.25)
    first_tick_count = len([e for e in received if e["type"] == "weather"])

    # Wait for the second tick
    await asyncio.sleep(0.25)
    second_tick_total = len([e for e in received if e["type"] == "weather"])

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert first_tick_count == 100, f"Expected 100 rows in first tick, got: {first_tick_count}"
    assert second_tick_total == 200, f"Expected 200 total after two ticks, got: {second_tick_total}"
