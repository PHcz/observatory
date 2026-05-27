"""TDD tests for observatory.weather.writer.write_reading (Phase 3-02).

Spec locked in 03-02-PLAN.md:
    - one row per envelope, BEGIN IMMEDIATE + INSERT OR IGNORE
    - dedup proven via UNIQUE(node_id, ts) from migration 0003
    - rowcount semantics: True iff cursor.rowcount == 1, else False
    - wifi_rssi always NULL (firmware doesn't publish)
    - DB errors caught, logged at ERROR (event=weather_write_error),
      function returns False (never raises) so the subscriber loop
      stays alive across transient SQLite faults.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from observatory.weather.payload import parse_envelope
from observatory.weather.writer import write_reading


def _query(db_path: Path, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def test_writes_single_row_with_field_mapping(tmp_db: Path, load_payload: Any) -> None:
    env = parse_envelope(load_payload("canonical_payload.json"))
    assert write_reading(env, db_path=str(tmp_db)) is True

    rows = _query(tmp_db, "SELECT * FROM weather")
    assert len(rows) == 1
    r = rows[0]
    assert r["node_id"] == "observatory-weather"
    assert r["temp_c"] == 18.4
    assert r["humidity_pct"] == 61.2
    assert r["pressure_hpa"] == 1012.3
    assert r["lux"] == 234.5
    assert r["battery_v"] == 2.7
    assert r["wifi_rssi"] is None


def test_ts_parsed_from_iso_timestamp(tmp_db: Path, load_payload: Any) -> None:
    env = parse_envelope(load_payload("canonical_payload.json"))
    assert write_reading(env, db_path=str(tmp_db)) is True

    rows = _query(tmp_db, "SELECT ts FROM weather")
    assert len(rows) == 1
    ts = rows[0]["ts"]
    assert isinstance(ts, int)
    # Roundtrip: "2026-05-27T12:00:00Z" -> epoch -> back to ISO
    iso = datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert iso == "2026-05-27T12:00:00Z"


def test_null_voltage_persists_as_null(tmp_db: Path, load_payload: Any) -> None:
    env = parse_envelope(load_payload("missing_voltage.json"))
    assert write_reading(env, db_path=str(tmp_db)) is True

    rows = _query(tmp_db, "SELECT battery_v FROM weather")
    assert len(rows) == 1
    assert rows[0]["battery_v"] is None


def test_wifi_rssi_always_null(tmp_db: Path, load_payload: Any) -> None:
    """Even on the canonical fixture (which has every other field), wifi_rssi must be NULL."""
    env = parse_envelope(load_payload("canonical_payload.json"))
    assert write_reading(env, db_path=str(tmp_db)) is True

    rows = _query(tmp_db, "SELECT wifi_rssi FROM weather")
    assert len(rows) == 1
    assert rows[0]["wifi_rssi"] is None


def test_duplicate_returns_false(tmp_db: Path, load_payload: Any) -> None:
    """Second write of the same (node_id, ts) returns False; row count stays 1."""
    env = parse_envelope(load_payload("canonical_payload.json"))
    assert write_reading(env, db_path=str(tmp_db)) is True
    assert write_reading(env, db_path=str(tmp_db)) is False

    rows = _query(tmp_db, "SELECT COUNT(*) AS n FROM weather")
    assert rows[0]["n"] == 1


def test_db_error_returns_false_no_raise(
    tmp_db: Path, load_payload: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A simulated sqlite3.OperationalError is caught, logged ERROR, returns False.

    The shared tests/weather/conftest.py autouse-configures structlog with
    cache_logger_on_first_use=True (Plan 03-00 deliverable), which defeats
    ``structlog.testing.capture_logs()``. We sidestep that by recording
    log calls directly on the writer module's bound logger.
    """
    env = parse_envelope(load_payload("canonical_payload.json"))

    def _broken(*_a: Any, **_kw: Any) -> Any:
        raise sqlite3.OperationalError("simulated db failure")

    monkeypatch.setattr("observatory.weather.writer.get_write_conn", _broken)

    recorded: list[tuple[str, dict[str, Any]]] = []

    class _RecordingLogger:
        def info(self, event: str, **kw: Any) -> None:
            recorded.append(("info", {"event": event, **kw}))

        def error(self, event: str, **kw: Any) -> None:
            recorded.append(("error", {"event": event, **kw}))

    monkeypatch.setattr("observatory.weather.writer.log", _RecordingLogger())

    result = write_reading(env, db_path=str(tmp_db))

    assert result is False
    assert any(
        level == "error" and entry["event"] == "weather_write_error" for level, entry in recorded
    ), f"expected weather_write_error at ERROR level, got: {recorded}"


def test_writes_to_configured_db_path(tmp_db: Path, load_payload: Any) -> None:
    """db_path kwarg routes the write to that exact file (not settings.observatory_db_path)."""
    env = parse_envelope(load_payload("canonical_payload.json"))
    assert write_reading(env, db_path=str(tmp_db)) is True

    rows = _query(tmp_db, "SELECT node_id FROM weather")
    assert len(rows) == 1
    assert rows[0]["node_id"] == "observatory-weather"
