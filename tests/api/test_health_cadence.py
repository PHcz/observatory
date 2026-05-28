"""UI-20 — /api/health includes cadence_warning per source (Plan 08-05)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_has_cadence_warning_for_local_sources(api_client: TestClient) -> None:
    r = api_client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    for source in ("weather", "muon"):
        assert source in body["local"], f"missing local source {source}"
        assert "cadence_warning" in body["local"][source]
        assert isinstance(body["local"][source]["cadence_warning"], bool)


def test_health_has_cadence_warning_for_external_sources(api_client: TestClient) -> None:
    r = api_client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    for source in ("usgs", "emsc", "bgs", "noaa", "blitzortung", "aurora"):
        assert source in body["external"], f"missing external source {source}"
        assert "cadence_warning" in body["external"][source]
        assert isinstance(body["external"][source]["cadence_warning"], bool)


def test_health_cadence_warning_false_when_no_events(api_client: TestClient) -> None:
    # Empty DB: last_event_ts is None for every source → cadence_warning must be False.
    r = api_client.get("/api/health")
    body = r.json()
    for source in ("weather", "muon"):
        assert body["local"][source]["last_event_ts"] is None
        assert body["local"][source]["cadence_warning"] is False
    for source in ("usgs", "emsc", "bgs", "noaa", "blitzortung", "aurora"):
        assert body["external"][source]["last_event_ts"] is None
        assert body["external"][source]["cadence_warning"] is False
