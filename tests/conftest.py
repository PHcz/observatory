"""Shared pytest fixtures for the observatory test suite.

Provides isolated tmp paths and env vars so tests don't touch the real
SQLite database, backup mount, or shell environment.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    """Return a temp path for a SQLite database file (not yet created)."""
    return tmp_path / "observatory.db"


@pytest.fixture
def tmp_backup_mount(tmp_path: Path) -> Path:
    """Return a temp directory that simulates the /mnt/backup mount point.

    NOTE: Path.is_mount() returns False for tmp dirs (they are not actual
    mountpoints), so backup tests that assert no-mount behaviour rely on
    this naturally. Tests that need to bypass the is_mount() check should
    monkeypatch backup.BACKUP_MOUNT and Path.is_mount accordingly.
    """
    d = tmp_path / "backup"
    d.mkdir()
    return d


@pytest.fixture
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Clear OBSERVATORY_* and HOME_LAT/HOME_LON env vars for this test."""
    for k in list(os.environ.keys()):
        if k.startswith("OBSERVATORY_") or k in {
            "HOME_LAT",
            "HOME_LON",
            "MQTT_BROKER_HOST",
            "MQTT_BROKER_PORT",
        }:
            monkeypatch.delenv(k, raising=False)
    yield


@pytest.fixture
def valid_env(monkeypatch: pytest.MonkeyPatch, tmp_db_path: Path) -> None:
    """Set a complete, valid set of env vars for Settings()."""
    monkeypatch.setenv("HOME_LAT", "51.5074")
    monkeypatch.setenv("HOME_LON", "-0.1278")
    monkeypatch.setenv("OBSERVATORY_DB_PATH", str(tmp_db_path))
    monkeypatch.setenv("MQTT_BROKER_HOST", "localhost")
    monkeypatch.setenv("MQTT_BROKER_PORT", "1883")
