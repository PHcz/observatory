"""Phase 16 ENH-02: GET /api/muon/diagnostics — data-quality diagnostics endpoint.

RED: /api/muon/diagnostics does not exist yet.
This test gates Wave 1 implementation.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from observatory.api.routers import muon as muon_router


@pytest.fixture
def client(_ensure_settings_loaded: Path) -> TestClient:
    app = FastAPI()
    app.include_router(muon_router.router, prefix="/api")
    return TestClient(app)


def test_muon_diagnostics_empty_db_returns_200(client: TestClient) -> None:
    """GET /api/muon/diagnostics on an empty DB returns 200 with required keys."""
    resp = client.get("/api/muon/diagnostics")
    assert resp.status_code == 200
    body = resp.json()
    assert "dt_histogram" in body, f"dt_histogram missing; keys: {list(body.keys())}"
    assert "rate_pmf" in body, f"rate_pmf missing; keys: {list(body.keys())}"
    assert "baseline_rate" in body, f"baseline_rate missing; keys: {list(body.keys())}"
    assert "sample_size_minutes" in body, f"sample_size_minutes missing; keys: {list(body.keys())}"


def test_muon_diagnostics_empty_state(client: TestClient) -> None:
    """On empty DB, dt_histogram and rate_pmf must be lists (possibly empty)."""
    resp = client.get("/api/muon/diagnostics")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["dt_histogram"], list)
    assert isinstance(body["rate_pmf"], list)
