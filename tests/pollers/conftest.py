"""Shared fixtures for tests/pollers/."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

import pytest

import observatory.config as _config_mod
from observatory.config import Settings
from observatory.logging import configure_logging

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_0001 = REPO_ROOT / "migrations" / "0001_initial_schema.sql"
SCHEMA_0002 = REPO_ROOT / "migrations" / "0002_poller_runs.sql"


@pytest.fixture(autouse=True)
def _configure_structlog() -> None:
    configure_logging(level="DEBUG")


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
