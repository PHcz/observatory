"""Smoke tests for the FastAPI app object + route mount."""

from __future__ import annotations

from fastapi.testclient import TestClient

from observatory.api.main import app


def test_app_metadata() -> None:
    assert app.title == "Observatory API"


def test_health_route_is_mounted_under_api_prefix() -> None:
    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/api/health" in paths


def test_health_endpoint_returns_200(api_client: TestClient) -> None:
    # Stub thermal so the smoke does not depend on vcgencmd on dev machines.
    import observatory.api.routers.health as _health_mod

    orig_pi = _health_mod._pi_block
    _health_mod._pi_block = lambda: {  # type: ignore[assignment]
        "temp_c": 42.1,
        "throttled": "0x0",
        "status": "healthy",
        "warnings": [],
    }
    try:
        r = api_client.get("/api/health")
    finally:
        _health_mod._pi_block = orig_pi  # type: ignore[assignment]
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) >= {"status", "timestamp", "local", "external", "pi"}
