"""Smoke test — fixtures spin up and pytest collection works."""

from __future__ import annotations

import pytest


@pytest.mark.integration
def test_integration_smoke(broker_host_port: tuple[str, int]) -> None:
    host, port = broker_host_port
    assert host
    assert 1024 <= port <= 65535
