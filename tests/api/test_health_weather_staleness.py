"""Verify /api/health reports weather staleness_threshold_sec=1800 + source per CONTEXT.md."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _stub_thermal_and_subscriber(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub vcgencmd (absent on dev macOS) + skip real subscriber for fast lifespan."""
    import observatory.api.routers.health as health_mod

    monkeypatch.setattr(health_mod, "read_temp_c", lambda: 42.0)
    monkeypatch.setattr(health_mod, "read_throttled", lambda: "0x0")

    async def _noop_sub(stop_event, db_path=None):  # type: ignore[no-untyped-def]
        await stop_event.wait()

    monkeypatch.setattr("observatory.weather.subscriber.run_subscriber", _noop_sub, raising=False)
    monkeypatch.setattr("observatory.api.main.run_subscriber", _noop_sub, raising=False)


def test_health_weather_staleness_is_1800(monkeypatch: pytest.MonkeyPatch) -> None:
    from observatory.api import main as main_mod

    _stub_thermal_and_subscriber(monkeypatch)

    with TestClient(main_mod.app) as client:
        r = client.get("/api/health")
        assert r.status_code == 200
        body = r.json()
        assert "weather" in body["local"]
        assert body["local"]["weather"]["staleness_threshold_sec"] == 1800


def test_health_weather_includes_source_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """CONTEXT.md §specifics example mandates a 'source' key on local.weather."""
    from observatory.api import main as main_mod

    _stub_thermal_and_subscriber(monkeypatch)

    with TestClient(main_mod.app) as client:
        r = client.get("/api/health")
        payload = r.json()
        # autouse Settings() defaults weather_nickname="observatory-weather"
        assert payload["local"]["weather"]["source"] == "observatory-weather"


def test_intervals_sec_weather_900() -> None:
    from observatory.api._freshness import HEALTHY_MULT, INTERVALS_SEC

    assert INTERVALS_SEC["weather"] == 900
    assert HEALTHY_MULT * INTERVALS_SEC["weather"] == 1800
