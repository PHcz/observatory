"""Shared fixtures for tests/weather/ (Phase 3 weather subscriber tests)."""

from __future__ import annotations

import logging
import sqlite3
import sys
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import structlog

import observatory.config as _config_mod
from observatory.config import Settings

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
SCHEMA_0001 = MIGRATIONS_DIR / "0001_initial_schema.sql"
SCHEMA_0003 = MIGRATIONS_DIR / "0003_weather_unique.sql"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(autouse=True)
def _configure_structlog(monkeypatch: pytest.MonkeyPatch) -> None:
    """Per-test structlog config WITHOUT cached loggers + no-op prod configure.

    Mirrors tests/pollers/conftest.py:22-69. Two interlocking issues this fixes:
      1. structlog.testing.capture_logs() patches the processor chain in
         place, but cached bound loggers retain a stale reference. We set
         cache_logger_on_first_use=False so the lazy proxy re-resolves
         each call and sees the LogCapture processor.
      2. Production code calls observatory.logging.configure_logging()
         which sets cache_logger_on_first_use=True — locking module
         loggers to the prod JSON-renderer chain. We monkeypatch
         configure_logging to a no-op so prod code doesn't fight us.
    """
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.DEBUG)
    structlog.reset_defaults()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
        cache_logger_on_first_use=False,
    )
    import observatory.logging as _obs_logging

    monkeypatch.setattr(_obs_logging, "configure_logging", lambda level="INFO": None)


@pytest.fixture(autouse=True)
def _ensure_settings_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    """Materialize observatory.config.settings for weather tests.

    The module-level singleton is None when import-time env is incomplete
    (HOME_LAT/HOME_LON not set globally). Weather library code reads
    settings.* at call time, so we install a valid Settings() with London
    placeholder coords for each test, and rebind the singleton in modules
    that captured `settings` by name on import.
    """
    monkeypatch.setenv("HOME_LAT", "51.5074")
    monkeypatch.setenv("HOME_LON", "-0.1278")
    s = Settings()
    monkeypatch.setattr(_config_mod, "settings", s)
    # Weather modules that imported `settings` by name — rebind their refs.
    import importlib

    for mod_path in (
        "observatory.weather.subscriber",
        "observatory.weather.writer",
        "observatory.weather.alerts.notifier",
        "observatory.weather.alerts.rules",
    ):
        try:
            _m = importlib.import_module(mod_path)
            monkeypatch.setattr(_m, "settings", s, raising=False)
        except ModuleNotFoundError:
            pass


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """Create a tmp SQLite DB with the weather schema applied (0001 + 0003)."""
    db_path = tmp_path / "test_observatory.db"
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.executescript(SCHEMA_0001.read_text())
    conn.executescript(SCHEMA_0003.read_text())
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.close()
    return db_path


@pytest.fixture
def load_payload() -> Callable[[str], bytes]:
    """Return a function that loads a tests/weather/fixtures/<name> file as bytes."""

    def _load(name: str) -> bytes:
        return (FIXTURES_DIR / name).read_bytes()

    return _load


@pytest.fixture
def fake_mqtt_message() -> Callable[[str, bytes], Any]:
    """Factory for a SimpleNamespace mimicking aiomqtt.Message (topic+payload only)."""

    def _make(topic: str, payload: bytes) -> Any:
        topic_obj = SimpleNamespace(value=topic)

        def _topic_str(self: Any = topic_obj) -> str:
            return str(self.value)

        topic_obj.__str__ = _topic_str  # type: ignore[method-assign]
        return SimpleNamespace(topic=topic_obj, payload=payload)

    return _make
