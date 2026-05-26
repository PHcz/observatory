"""Smoke tests for the FastAPI app object + route mount.

Phase 5 tests (existing):
  - test_app_metadata
  - test_health_route_is_mounted_under_api_prefix
  - test_health_endpoint_returns_200

Phase 6 Plan 06-07 tests (new):
  - test_app_version_0_2_0
  - test_docs_url_disabled_in_production
  - test_all_expected_routes_present
  - test_health_returns_200_via_lifespan_client
  - test_current_returns_200_with_astronomy_key
  - test_websocket_snapshot_on_connect
  - test_static_bundle_missing_no_slash_mount
  - test_origin_allowlist_middleware_installed
  - test_lifespan_attached
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from observatory.api.main import app

# ---------------------------------------------------------------------------
# Phase 5 smoke tests (MUST keep passing)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Phase 6 Plan 06-07 tests (new)
# ---------------------------------------------------------------------------


def test_app_version_0_2_0() -> None:
    """App title and version reflect Phase 6 wiring."""
    assert app.title == "Observatory API"
    assert app.version == "0.2.0"


def test_docs_url_disabled_in_production() -> None:
    """OBS_ENV defaults to 'production' — docs_url must be None."""
    assert app.docs_url is None


def test_all_expected_routes_present() -> None:
    """All 10 router paths + /ws must be registered."""
    paths = {getattr(r, "path", None) for r in app.routes}
    required = {
        "/api/health",
        "/api/current",
        "/api/weather",
        "/api/muon",
        "/api/earthquakes",
        "/api/space-weather",
        "/api/space-weather/current",
        "/api/lightning/summary",
        "/api/aurora/current",
        "/api/events/recent",
        "/api/stats/today",
        "/ws",
    }
    missing = required - paths
    assert not missing, f"Missing routes: {missing}"


def test_health_returns_200_via_lifespan_client() -> None:
    """TestClient context-manager form triggers lifespan; /api/health must 200."""
    import observatory.api.routers.health as _health_mod

    orig_pi = _health_mod._pi_block
    _health_mod._pi_block = lambda: {  # type: ignore[assignment]
        "temp_c": 42.1,
        "throttled": "0x0",
        "status": "healthy",
        "warnings": [],
    }
    try:
        with TestClient(app) as client:
            r = client.get("/api/health")
    finally:
        _health_mod._pi_block = orig_pi  # type: ignore[assignment]
    assert r.status_code == 200


def test_current_returns_200_with_astronomy_key() -> None:
    """GET /api/current returns 200 and body includes 'astronomy' key."""
    with TestClient(app) as client:
        r = client.get("/api/current")
    assert r.status_code == 200
    assert "astronomy" in r.json()


def test_websocket_snapshot_on_connect() -> None:
    """WebSocket first frame must be type='snapshot'."""
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            msg = ws.receive_json()
    assert msg["type"] == "snapshot"


def test_static_bundle_missing_no_slash_mount(monkeypatch: pytest.MonkeyPatch) -> None:
    """When api_static_bundle_dir points at a nonexistent path, no '/' mount is added.

    We check that the app imported with the default settings (where
    /opt/observatory/frontend/build doesn't exist on dev/CI) does NOT have a
    StaticFiles mount at '/'.
    """
    import starlette.routing

    slash_mounts = [
        r for r in app.routes if isinstance(r, starlette.routing.Mount) and r.path == "/"
    ]
    # On dev/CI the bundle dir won't exist — no slash mount should be present.
    # (If running on a Pi with the built bundle, this test would be skipped/modified.)
    assert slash_mounts == [], "StaticFiles at '/' should NOT be mounted when bundle dir is missing"


def test_origin_allowlist_middleware_installed() -> None:
    """OriginAllowlistMiddleware must be in app.user_middleware."""
    assert any(m.cls.__name__ == "OriginAllowlistMiddleware" for m in app.user_middleware), (
        "OriginAllowlistMiddleware not found in app.user_middleware"
    )


def test_lifespan_attached() -> None:
    """app.router.lifespan_context must not be None."""
    assert app.router.lifespan_context is not None
