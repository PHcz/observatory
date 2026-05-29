"""Integration test fixtures — real Mosquitto + real SQLite + real FastAPI.

Marked `integration`; excluded from default ``pytest`` via pyproject addopts.
Run explicitly: ``pytest -m integration`` (CI / pre-release gate).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from testcontainers.mqtt import MosquittoContainer

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.fixture(scope="session")
def mosquitto_broker() -> Iterator[MosquittoContainer]:
    """Session-scoped Mosquitto container; eclipse-mosquitto:2 image."""
    container = MosquittoContainer(image="eclipse-mosquitto:2")
    container.start()
    try:
        yield container
    finally:
        container.stop()


@pytest.fixture
def broker_host_port(mosquitto_broker: MosquittoContainer) -> tuple[str, int]:
    """Resolve dynamic host + port for the started container."""
    host = mosquitto_broker.get_container_host_ip()
    port = int(mosquitto_broker.get_exposed_port(1883))
    return host, port


@pytest.fixture
def tmp_db_with_migrations(tmp_path: Path) -> Path:
    """Tmp SQLite path with all migrations 0001+0002+0003 applied via executescript."""
    db_path = tmp_path / "observatory.db"
    conn = sqlite3.connect(db_path)
    try:
        for sql_file in sorted(MIGRATIONS_DIR.glob("000*.sql")):
            conn.executescript(sql_file.read_text())
        conn.commit()
    finally:
        conn.close()
    return db_path


@pytest.fixture
def integration_settings(
    monkeypatch: pytest.MonkeyPatch,
    broker_host_port: tuple[str, int],
    tmp_db_with_migrations: Path,
) -> None:
    """Rebind observatory.config.settings to use the container's broker + tmp DB.

    Also rebinds the same ``settings`` instance onto every module that took an
    import-time copy (subscriber, ws router, db_watcher, current router, health
    router, thermal helper) — same pattern as tests/api/conftest.py
    ``_ensure_settings_loaded``. Without this, those modules keep their original
    ``settings`` and the integration test bypasses the env overrides.
    """
    host, port = broker_host_port
    monkeypatch.setenv("HOME_LAT", "51.5074")
    monkeypatch.setenv("HOME_LON", "-0.1278")
    monkeypatch.setenv("MQTT_BROKER_HOST", host)
    monkeypatch.setenv("MQTT_BROKER_PORT", str(port))
    monkeypatch.setenv("OBSERVATORY_DB_PATH", str(tmp_db_with_migrations))
    # Faster db_watcher poll so Pipeline B doesn't burn 5s per tick.
    monkeypatch.setenv("API_DB_WATCHER_INTERVAL_SEC", "0.25")

    # Rebind module-level singleton; see tests/weather/conftest.py for the
    # same pattern used for unit tests.
    import observatory.config as cfg_mod

    new_settings = cfg_mod.Settings()
    monkeypatch.setattr(cfg_mod, "settings", new_settings)

    # Rebind all import-time copies — mirrors tests/api/conftest.py.
    import observatory.api.db_watcher as _db_watcher_mod
    import observatory.api.routers.current as _current_mod
    import observatory.api.routers.health as _health_mod
    import observatory.api.routers.ws as _ws_mod
    import observatory.pi.thermal as _thermal_mod
    import observatory.weather.subscriber as _sub_mod

    for mod in (_sub_mod, _ws_mod, _db_watcher_mod, _current_mod, _health_mod, _thermal_mod):
        monkeypatch.setattr(mod, "settings", new_settings, raising=False)
