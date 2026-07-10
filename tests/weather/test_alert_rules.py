"""Phase 16 ENH-04: weather alert rules — frost and rapid-pressure-fall.

RED: imports from observatory.weather.alerts.rules which does not exist yet.
This test gates Wave 1 implementation.

Tests use an in-memory SQLite database seeded with weather rows.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import observatory.config as _cfg
import observatory.weather.alerts.rules as _rules_mod
from observatory.weather.alerts.rules import (
    AlertResult,
    FrostRule,
    IndoorCo2Rule,
    PressureFallRule,
    StaleEnviroRule,
    _format_age,
    _within_alert_window,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_0001 = REPO_ROOT / "migrations" / "0001_initial_schema.sql"
MIGRATION_0010 = REPO_ROOT / "migrations" / "0010_indoor_air.sql"


def _make_db() -> sqlite3.Connection:
    """Create an in-memory DB with the weather table from migration 0001."""
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.executescript(SCHEMA_0001.read_text())
    return conn


def _insert_weather(
    conn: sqlite3.Connection,
    ts: int,
    temp_c: float,
    humidity_pct: float,
    pressure_hpa: float,
    node_id: str = "test-node",
) -> None:
    conn.execute(
        "INSERT INTO weather (node_id, ts, temp_c, humidity_pct, pressure_hpa) "
        "VALUES (?, ?, ?, ?, ?)",
        (node_id, ts, temp_c, humidity_pct, pressure_hpa),
    )


class TestFrostRule:
    def test_frost_rule_triggered(self) -> None:
        """temp 1°C + humidity 95% → dewpoint ≈ 0.25°C (spread < 2°C) → frost triggered."""
        conn = _make_db()
        now = int(time.time())
        # dewpoint = temp - (100 - RH) / 5 = 1.0 - (100-95)/5 = 1.0 - 1.0 = 0.0
        # spread = temp - dewpoint = 1.0 - 0.0 = 1.0 < 2.0 threshold → triggered
        _insert_weather(conn, now, temp_c=1.0, humidity_pct=95.0, pressure_hpa=1013.0)
        conn.commit()
        rule = FrostRule()
        result = rule.evaluate(conn)
        assert isinstance(result, AlertResult)
        assert result.triggered is True
        assert result.rule == "frost_risk"

    def test_frost_not_triggered_warm(self) -> None:
        """temp 10°C → well above frost threshold, not triggered."""
        conn = _make_db()
        now = int(time.time())
        _insert_weather(conn, now, temp_c=10.0, humidity_pct=70.0, pressure_hpa=1013.0)
        conn.commit()
        rule = FrostRule()
        result = rule.evaluate(conn)
        assert result.triggered is False

    def test_frost_not_triggered_dry(self) -> None:
        """temp 1°C but very dry (low humidity → large dewpoint spread) → not triggered."""
        conn = _make_db()
        now = int(time.time())
        # dewpoint = 1.0 - (100-30)/5 = 1.0 - 14.0 = -13.0, spread = 14.0 > 2.0
        _insert_weather(conn, now, temp_c=1.0, humidity_pct=30.0, pressure_hpa=1013.0)
        conn.commit()
        rule = FrostRule()
        result = rule.evaluate(conn)
        assert result.triggered is False

    def test_frost_empty_db(self) -> None:
        """Empty weather table → not triggered (no data to evaluate)."""
        conn = _make_db()
        rule = FrostRule()
        result = rule.evaluate(conn)
        assert result.triggered is False


class TestPressureFallRule:
    def test_pressure_fall_triggered(self) -> None:
        """Pressure 3h ago=1015, now=1012 → delta=-3.0 < -1.6 → triggered."""
        conn = _make_db()
        now = int(time.time())
        three_h_ago = now - 3 * 3600
        _insert_weather(conn, three_h_ago, temp_c=15.0, humidity_pct=70.0, pressure_hpa=1015.0)
        _insert_weather(conn, now, temp_c=15.0, humidity_pct=70.0, pressure_hpa=1012.0)
        conn.commit()
        rule = PressureFallRule()
        result = rule.evaluate(conn)
        assert isinstance(result, AlertResult)
        assert result.triggered is True
        assert result.rule == "rapid_pressure_fall"

    def test_pressure_fall_not_triggered_slow(self) -> None:
        """Pressure drop of 0.5 hPa/3h is within threshold → not triggered."""
        conn = _make_db()
        now = int(time.time())
        three_h_ago = now - 3 * 3600
        _insert_weather(conn, three_h_ago, temp_c=15.0, humidity_pct=70.0, pressure_hpa=1013.5)
        _insert_weather(conn, now, temp_c=15.0, humidity_pct=70.0, pressure_hpa=1013.0)
        conn.commit()
        rule = PressureFallRule()
        result = rule.evaluate(conn)
        assert result.triggered is False

    def test_pressure_fall_rising_not_triggered(self) -> None:
        """Rising pressure → not triggered."""
        conn = _make_db()
        now = int(time.time())
        three_h_ago = now - 3 * 3600
        _insert_weather(conn, three_h_ago, temp_c=15.0, humidity_pct=70.0, pressure_hpa=1010.0)
        _insert_weather(conn, now, temp_c=15.0, humidity_pct=70.0, pressure_hpa=1015.0)
        conn.commit()
        rule = PressureFallRule()
        result = rule.evaluate(conn)
        assert result.triggered is False

    def test_pressure_fall_empty_db(self) -> None:
        """Empty weather table → not triggered."""
        conn = _make_db()
        rule = PressureFallRule()
        result = rule.evaluate(conn)
        assert result.triggered is False


class TestStaleEnviroRule:
    def test_stale_when_last_reading_older_than_threshold(self) -> None:
        """Default threshold 3600 s; a reading 2 h old → triggered."""
        conn = _make_db()
        now = int(time.time())
        _insert_weather(conn, now - 2 * 3600, temp_c=15.0, humidity_pct=70.0, pressure_hpa=1013.0)
        conn.commit()
        result = StaleEnviroRule().evaluate(conn)
        assert result.rule == "enviro_stale"
        assert result.triggered is True
        assert "No reading from Enviro" in result.detail

    def test_fresh_reading_not_triggered(self) -> None:
        """A reading 30 s old → well within threshold → not triggered."""
        conn = _make_db()
        now = int(time.time())
        _insert_weather(conn, now - 30, temp_c=15.0, humidity_pct=70.0, pressure_hpa=1013.0)
        conn.commit()
        assert StaleEnviroRule().evaluate(conn).triggered is False

    def test_empty_db_not_triggered(self) -> None:
        """No reading ever → nothing to be stale against → not triggered (no boot noise)."""
        conn = _make_db()
        assert StaleEnviroRule().evaluate(conn).triggered is False

    def test_threshold_is_config_driven(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        """A 10-min-old reading is stale once the threshold is tightened to 5 min."""
        import observatory.config as _config_mod

        monkeypatch.setattr(_config_mod.settings, "alert_enviro_stale_sec", 300)
        conn = _make_db()
        now = int(time.time())
        _insert_weather(conn, now - 600, temp_c=15.0, humidity_pct=70.0, pressure_hpa=1013.0)
        conn.commit()
        assert StaleEnviroRule().evaluate(conn).triggered is True


class TestFormatAge:
    def test_seconds(self) -> None:
        assert _format_age(45) == "45 s"

    def test_minutes(self) -> None:
        assert _format_age(45 * 60) == "45 m"

    def test_hours_and_minutes(self) -> None:
        assert _format_age(18 * 3600 + 20 * 60) == "18 h 20 m"

    def test_whole_hours(self) -> None:
        assert _format_age(3 * 3600) == "3 h"


class TestWithinAlertWindow:
    def test_in_window(self) -> None:
        assert _within_alert_window(12, 6, 22) is True

    def test_before_start_excluded(self) -> None:
        assert _within_alert_window(5, 6, 22) is False

    def test_end_hour_excluded(self) -> None:
        assert _within_alert_window(22, 6, 22) is False  # [start, end)

    def test_start_hour_included(self) -> None:
        assert _within_alert_window(6, 6, 22) is True

    def test_midnight_crossing_window(self) -> None:
        # e.g. a 22:00-06:00 window
        assert _within_alert_window(23, 22, 6) is True
        assert _within_alert_window(3, 22, 6) is True
        assert _within_alert_window(12, 22, 6) is False


class TestIndoorCo2Rule:
    def _db(self) -> sqlite3.Connection:
        conn = _make_db()  # weather table from 0001
        conn.executescript(MIGRATION_0010.read_text())  # + indoor_air
        return conn

    def _insert(self, conn: sqlite3.Connection, co2: int, node: str = "living-room") -> None:
        conn.execute(
            "INSERT INTO indoor_air (node_id, ts, co2_ppm) VALUES (?, ?, ?)",
            (node, int(time.time()), co2),
        )
        conn.commit()

    def test_triggered_when_red_in_window(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr(_rules_mod, "_current_hour", lambda: 12)  # midday
        conn = self._db()
        self._insert(conn, 1300)
        r = IndoorCo2Rule().evaluate(conn)
        assert r.rule == "indoor_co2_high"
        assert r.triggered is True
        assert "1300" in r.detail

    def test_not_triggered_below_threshold(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr(_rules_mod, "_current_hour", lambda: 12)
        conn = self._db()
        self._insert(conn, 900)
        assert IndoorCo2Rule().evaluate(conn).triggered is False

    def test_not_triggered_outside_window_even_if_red(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr(_rules_mod, "_current_hour", lambda: 3)  # 3am — quiet hours
        conn = self._db()
        self._insert(conn, 1500)
        assert IndoorCo2Rule().evaluate(conn).triggered is False

    def test_empty_not_triggered(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr(_rules_mod, "_current_hour", lambda: 12)
        conn = self._db()
        assert IndoorCo2Rule().evaluate(conn).triggered is False

    def test_threshold_is_config_driven(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setattr(_rules_mod, "_current_hour", lambda: 12)
        monkeypatch.setattr(_cfg.settings, "alert_co2_red_ppm", 1000)
        conn = self._db()
        self._insert(conn, 1100)  # above the tightened 1000 threshold
        assert IndoorCo2Rule().evaluate(conn).triggered is True
