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
    """Rebind observatory.config.settings to use the container's broker + tmp DB."""
    host, port = broker_host_port
    monkeypatch.setenv("HOME_LAT", "51.5074")
    monkeypatch.setenv("HOME_LON", "-0.1278")
    monkeypatch.setenv("MQTT_BROKER_HOST", host)
    monkeypatch.setenv("MQTT_BROKER_PORT", str(port))
    monkeypatch.setenv("OBSERVATORY_DB_PATH", str(tmp_db_with_migrations))
    # Rebind module-level singleton; see tests/weather/conftest.py for the
    # same pattern used for unit tests.
    import observatory.config as cfg_mod

    cfg_mod.settings = cfg_mod.Settings()
