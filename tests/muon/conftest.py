"""Shared fixtures for tests/muon/."""

from __future__ import annotations

import os
import pty
import sqlite3
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from observatory.logging import configure_logging

SCHEMA = Path(__file__).resolve().parents[2] / "migrations" / "0001_initial_schema.sql"


@pytest.fixture(autouse=True)
def _configure_structlog() -> None:
    """Ensure structlog is configured so capsys can see JSON log output."""
    configure_logging(level="DEBUG")


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """Create a tmp SQLite DB with the muon_events schema applied. Returns path."""
    db_path = tmp_path / "test_observatory.db"
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.executescript(SCHEMA.read_text())
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.close()
    return db_path


@pytest.fixture
def pty_pair() -> Iterator[tuple[int, str]]:
    """Open a pseudo-terminal. Yields (master_fd, slave_path). Master end stays open
    for the test to write to; slave_path is what the reader opens as if it were
    /dev/picomuon. Slave fd is closed immediately — master fd keeps the pty alive."""
    master_fd, slave_fd = pty.openpty()
    slave_path = os.ttyname(slave_fd)
    os.close(slave_fd)
    try:
        yield master_fd, slave_path
    finally:
        try:
            os.close(master_fd)
        except OSError:
            pass


class FakeSystemdNotifier:
    """Stand-in for sdnotify.SystemdNotifier — records every notify() call."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def notify(self, message: str) -> None:
        self.calls.append(message)


@pytest.fixture
def fake_sdnotify() -> FakeSystemdNotifier:
    return FakeSystemdNotifier()


@pytest.fixture
def load_fixture() -> Callable[[str], str]:
    """Return a function that loads a tests/fixtures/muon/<name> file as text."""
    fixtures_dir = Path(__file__).resolve().parents[1] / "fixtures" / "muon"

    def _load(name: str) -> str:
        return (fixtures_dir / name).read_text()

    return _load
