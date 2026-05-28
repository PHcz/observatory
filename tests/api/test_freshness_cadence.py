"""UI-20 — cadence_warning helper (Plan 08-05)."""

from __future__ import annotations

import pytest

import observatory.config as _config_mod
from observatory.api._freshness import EXPECTED_INTERVAL_SEC, cadence_warning


def test_cadence_warning_returns_false_when_last_event_none() -> None:
    assert cadence_warning(now=1000, last_event_ts=None, source="weather") is False


def test_cadence_warning_weather_fresh() -> None:
    # age=100, expected=1500 (default), threshold=3000 → fresh
    assert cadence_warning(now=1000, last_event_ts=900, source="weather") is False


def test_cadence_warning_weather_overdue() -> None:
    # age=5000, expected=1500, threshold=3000 → overdue
    assert cadence_warning(now=10000, last_event_ts=5000, source="weather") is True


def test_cadence_warning_weather_bench_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_config_mod.settings, "weather_expected_upload_sec", 300)
    # age=1000, expected=300, threshold=600 → overdue
    assert cadence_warning(now=1500, last_event_ts=500, source="weather") is True


def test_cadence_warning_muon_fresh() -> None:
    # age=50, expected=60, threshold=120 → fresh
    assert cadence_warning(now=1000, last_event_ts=950, source="muon") is False


def test_cadence_warning_muon_overdue() -> None:
    # age=500, expected=60, threshold=120 → overdue
    assert cadence_warning(now=1000, last_event_ts=500, source="muon") is True


def test_cadence_warning_unknown_source() -> None:
    assert cadence_warning(now=1000, last_event_ts=500, source="unknown") is False


def test_expected_interval_sec_keys() -> None:
    # Locks the known external-source keyset (weather handled dynamically).
    assert set(EXPECTED_INTERVAL_SEC.keys()) == {
        "muon",
        "usgs",
        "emsc",
        "bgs",
        "noaa",
        "blitzortung",
        "aurora",
    }
