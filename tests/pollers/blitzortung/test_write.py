"""Tests for write_lightning_batch + LightningStrike dataclass."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

import observatory.pollers._write as _write_mod


@pytest.fixture
def patched_db(monkeypatch: pytest.MonkeyPatch, tmp_db: Path) -> Path:
    def _conn(_db_path: str | None = None) -> sqlite3.Connection:
        c = sqlite3.connect(str(tmp_db), isolation_level=None)
        c.execute("PRAGMA foreign_keys=ON")
        return c

    monkeypatch.setattr(_write_mod, "get_write_conn", _conn)
    return tmp_db


def _query(db_path: Path, sql: str) -> list[tuple[object, ...]]:
    with sqlite3.connect(str(db_path)) as c:
        return c.execute(sql).fetchall()


def test_lightning_strike_dataclass_is_frozen() -> None:
    from dataclasses import FrozenInstanceError

    from observatory.pollers._types import LightningStrike

    s = LightningStrike(ts=1, latitude=51.5, longitude=-0.1, distance_km=10.0)
    with pytest.raises((FrozenInstanceError, AttributeError)):
        s.ts = 2  # type: ignore[misc]


def test_write_lightning_batch_inserts_rows(patched_db: Path) -> None:
    from observatory.pollers._types import LightningStrike
    from observatory.pollers._write import write_lightning_batch

    strikes = [
        LightningStrike(ts=1779700000, latitude=51.5, longitude=-0.1, distance_km=10.0),
        LightningStrike(ts=1779700005, latitude=51.6, longitude=-0.2, distance_km=25.0),
        LightningStrike(ts=1779700010, latitude=51.7, longitude=-0.3, distance_km=40.0),
    ]
    fetched, written = write_lightning_batch(strikes, int(time.time()), "success")
    assert (fetched, written) == (3, 3)

    rows = _query(
        patched_db,
        "SELECT ts, latitude, longitude, distance_km FROM lightning_strikes ORDER BY ts",
    )
    assert rows == [
        (1779700000, 51.5, -0.1, 10.0),
        (1779700005, 51.6, -0.2, 25.0),
        (1779700010, 51.7, -0.3, 40.0),
    ]


def test_write_lightning_batch_empty_still_emits_audit(patched_db: Path) -> None:
    from observatory.pollers._write import write_lightning_batch

    fetched, written = write_lightning_batch([], int(time.time()), "success")
    assert (fetched, written) == (0, 0)

    runs = _query(
        patched_db,
        "SELECT source, events_fetched, events_written, status FROM poller_runs",
    )
    assert runs == [("blitzortung", 0, 0, "success")]


def test_write_lightning_batch_records_error_summary(patched_db: Path) -> None:
    from observatory.pollers._write import write_lightning_batch

    write_lightning_batch([], int(time.time()), "transient_fail", error_summary="ws_connect_failed")

    runs = _query(
        patched_db,
        "SELECT status, error_summary FROM poller_runs WHERE source='blitzortung'",
    )
    assert runs == [("transient_fail", "ws_connect_failed")]
