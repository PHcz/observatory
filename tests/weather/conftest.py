"""Shared fixtures for tests/weather/ (Phase 3 weather subscriber tests)."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from observatory.logging import configure_logging

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
SCHEMA_0001 = MIGRATIONS_DIR / "0001_initial_schema.sql"
SCHEMA_0003 = MIGRATIONS_DIR / "0003_weather_unique.sql"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(autouse=True)
def _configure_structlog() -> None:
    """Ensure structlog is configured so capsys can see JSON log output."""
    configure_logging(level="DEBUG")


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
        topic_obj.__str__ = lambda self=topic_obj: self.value  # type: ignore[assignment]
        return SimpleNamespace(topic=topic_obj, payload=payload)

    return _make
