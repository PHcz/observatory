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
# Every migration, in order -- a hand-maintained list silently missed new
# migrations (0011 broke ~50 API tests that touch space_weather).
MIGRATIONS = sorted((REPO_ROOT / "migrations").glob("[0-9][0-9][0-9][0-9]_*.sql"))


@pytest.fixture(autouse=True)
def _ensure_settings_loaded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Materialize observatory.config.settings for api tests + tmp_db override."""
    db_path = tmp_path / "api_test.db"
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    for migration in MIGRATIONS:
        conn.executescript(migration.read_text())
    conn.execute("PRAGMA journal_mode=WAL")
    conn.close()

    monkeypatch.setenv("HOME_LAT", "51.5074")
    monkeypatch.setenv("HOME_LON", "-0.1278")
    monkeypatch.setenv("OBSERVATORY_DB_PATH", str(db_path))
    # Starlette's TestClient always sends `Host: testserver` (its WebSocket path
    # hard-codes ws://testserver), so the test env -- and only the test env --
    # adds it to the production default for HostAllowlistMiddleware.
    monkeypatch.setenv(
        "API_ORIGIN_ALLOWLIST",
        Settings.model_fields["api_origin_allowlist"].default + ",testserver",
    )
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

    # Rebind muon router — Phase 16 ENH-01 reads settings.effective_area_cm2.
    import observatory.api.routers.muon as _muon_mod

    monkeypatch.setattr(_muon_mod, "settings", s, raising=False)

    # Rebind db_watcher — used by lifespan; reads settings.api_db_watcher_interval_sec.
    import observatory.api.db_watcher as _db_watcher_mod

    monkeypatch.setattr(_db_watcher_mod, "settings", s, raising=False)

    # Rebind ws router — reads settings.api_ws_queue_maxsize/ping/pong at request time.
    import observatory.api.routers.ws as _ws_mod

    monkeypatch.setattr(_ws_mod, "settings", s, raising=False)

    # Rebind weather router — Phase 16 ENH-05 reads settings.home_timezone
    # and settings.station_altitude_m for /api/weather/today + /api/weather/outlook.
    import observatory.api.routers.weather as _weather_mod

    monkeypatch.setattr(_weather_mod, "settings", s, raising=False)

    return db_path


@pytest.fixture
def health_db(_ensure_settings_loaded: Path) -> Path:
    """Path to the per-test SQLite DB seeded by the autouse fixture."""
    return _ensure_settings_loaded


@pytest.fixture
def api_client() -> TestClient:
    return TestClient(app)
