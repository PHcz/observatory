"""Shared FastAPI test fixtures.

Provides:
  - `api_client`: TestClient against the live `observatory.api.main.app`.
  - `_ensure_settings_loaded` (autouse): mirrors tests/pi/conftest.py — installs a
    valid Settings() so health-router code reading `settings.*` at request time
    works, and HOME_LAT/HOME_LON env defaults are present.
  - `health_db` (autouse): a tmp_path SQLite with both 0001 + 0002 migrations
    applied. Rebinds `settings.observatory_db_path` AND patches the health
    router's `get_conn` to use the tmp file so every TestClient request hits it.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import observatory.config as _config_mod
from observatory.api.main import app
from observatory.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_0001 = REPO_ROOT / "migrations" / "0001_initial_schema.sql"
SCHEMA_0002 = REPO_ROOT / "migrations" / "0002_poller_runs.sql"
# Phase 8.5 UI-18: /api/earthquakes router selects is_local; api tmp_db must carry it.
SCHEMA_0004 = REPO_ROOT / "migrations" / "0004_earthquakes_is_local.sql"
# Phase 10 FCAST-02: /api/forecast router reads forecast_* tables; api tmp_db must carry them.
SCHEMA_0005 = REPO_ROOT / "migrations" / "0005_forecast.sql"
# Phase 11 OAQ-02: /api/air-quality + /api/health read air_quality* tables; tmp_db must carry them.
SCHEMA_0006 = REPO_ROOT / "migrations" / "0006_air_quality.sql"
# Phase 13 MU2-06: /api/nmdb + /api/forbush + /api/health read nmdb* tables; tmp_db must carry them.
SCHEMA_0007 = REPO_ROOT / "migrations" / "0007_nmdb.sql"


@pytest.fixture(autouse=True)
def _ensure_settings_loaded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Materialize observatory.config.settings for api tests + tmp_db override."""
    db_path = tmp_path / "api_test.db"
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.executescript(SCHEMA_0001.read_text())
    conn.executescript(SCHEMA_0002.read_text())
    conn.executescript(SCHEMA_0004.read_text())
    conn.executescript(SCHEMA_0005.read_text())
    conn.executescript(SCHEMA_0006.read_text())
    conn.executescript(SCHEMA_0007.read_text())
    conn.execute("PRAGMA journal_mode=WAL")
    conn.close()

    monkeypatch.setenv("HOME_LAT", "51.5074")
    monkeypatch.setenv("HOME_LON", "-0.1278")
    monkeypatch.setenv("OBSERVATORY_DB_PATH", str(db_path))
    s = Settings()
    monkeypatch.setattr(_config_mod, "settings", s)

    # Rebind `settings` (and thermal helpers we'll commonly stub) on the
    # health router module so by-name imports see the test instance.
    import observatory.api.routers.health as _health_mod

    monkeypatch.setattr(_health_mod, "settings", s, raising=False)

    # Rebind on current router (06-05) — uses settings.home_lat/home_lon.
    import observatory.api.routers.current as _current_mod

    monkeypatch.setattr(_current_mod, "settings", s, raising=False)

    # Also rebind thermal module's settings so derive_status thresholds are valid.
    import observatory.pi.thermal as _thermal_mod

    monkeypatch.setattr(_thermal_mod, "settings", s, raising=False)

    # Rebind db_watcher — used by lifespan; reads settings.api_db_watcher_interval_sec.
    import observatory.api.db_watcher as _db_watcher_mod

    monkeypatch.setattr(_db_watcher_mod, "settings", s, raising=False)

    # Rebind ws router — reads settings.api_ws_queue_maxsize/ping/pong at request time.
    import observatory.api.routers.ws as _ws_mod

    monkeypatch.setattr(_ws_mod, "settings", s, raising=False)

    return db_path


@pytest.fixture
def health_db(_ensure_settings_loaded: Path) -> Path:
    """Path to the per-test SQLite DB seeded by the autouse fixture."""
    return _ensure_settings_loaded


@pytest.fixture
def api_client() -> TestClient:
    return TestClient(app)
