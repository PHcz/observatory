"""Shared fixtures for tests/pollers/."""

from __future__ import annotations

import logging
import sqlite3
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
import structlog

import observatory.config as _config_mod
from observatory.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_0001 = REPO_ROOT / "migrations" / "0001_initial_schema.sql"
SCHEMA_0002 = REPO_ROOT / "migrations" / "0002_poller_runs.sql"


@pytest.fixture(autouse=True)
def _configure_structlog() -> None:
    """Per-test structlog config WITHOUT cached loggers.

    structlog.testing.capture_logs() patches the processor chain at the
    config level, but cached bound loggers retain a reference to the
    pre-patch chain — so tests using capture_logs would see no events.
    Disabling logger caching keeps capture_logs working across all tests.
    """
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.DEBUG)
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


@pytest.fixture(autouse=True)
def _ensure_settings_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    """Materialize observatory.config.settings for pollers tests.

    The module-level singleton is None when import-time env is incomplete
    (typical in this repo where HOME_LAT/HOME_LON are not set globally).
    Poller library code reads `settings.poller_*` at call time, so we
    install a valid Settings() with London placeholder coords for the
    duration of each test.
    """
    monkeypatch.setenv("HOME_LAT", "51.5074")
    monkeypatch.setenv("HOME_LON", "-0.1278")
    s = Settings()
    monkeypatch.setattr(_config_mod, "settings", s)
    # Poller modules import `settings` by name at module load — patch their refs too
    import observatory.pollers._http as _http_mod
    import observatory.pollers._write as _write_mod

    monkeypatch.setattr(_http_mod, "settings", s, raising=False)
    monkeypatch.setattr(_write_mod, "settings", s, raising=False)
    # Per-source poller __main__ modules also capture `settings` by name on
    # import; rebind them defensively (raising=False so this is a no-op for
    # sources whose main hasn't shipped yet).
    import importlib

    for mod_path in (
        "observatory.pollers.usgs.__main__",
        "observatory.pollers.emsc.__main__",
        "observatory.pollers.bgs.__main__",
    ):
        try:
            _m = importlib.import_module(mod_path)
            monkeypatch.setattr(_m, "settings", s, raising=False)
        except ModuleNotFoundError:
            pass


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """Tmp SQLite with BOTH the initial schema AND poller_runs applied."""
    db_path = tmp_path / "test_observatory.db"
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.executescript(SCHEMA_0001.read_text())
    conn.executescript(SCHEMA_0002.read_text())
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.close()
    return db_path


@pytest.fixture
def load_eq_fixture() -> Callable[[str], bytes]:
    """Return a function loading tests/fixtures/earthquakes/<rel> as bytes."""
    fixtures_dir = REPO_ROOT / "tests" / "fixtures" / "earthquakes"

    def _load(rel: str) -> bytes:
        return (fixtures_dir / rel).read_bytes()

    return _load
