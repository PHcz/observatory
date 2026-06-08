"""Phase 16 ENH-06: POST /ingest HTTP fallback endpoint.

RED: /ingest does not exist yet.
This test gates Wave 1 implementation.

Tests:
- test_ingest_success: valid payload + correct auth → 201, row in weather table
- test_ingest_dedup: same payload twice → 2xx, row count unchanged (UNIQUE constraint)
- test_ingest_unauth: no/wrong auth → 401
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import observatory.config as _config_mod
from observatory.api.routers import ingest as ingest_router
from observatory.config import Settings


@pytest.fixture
def client_with_auth(_ensure_settings_loaded: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient with ingest basic auth configured."""
    # Configure a known password for testing
    monkeypatch.setenv("OBSERVATORY_INGEST_BASIC_AUTH_USER", "enviro")
    monkeypatch.setenv("OBSERVATORY_INGEST_BASIC_AUTH_PASSWORD", "test-secret-123")
    monkeypatch.setenv("HOME_LAT", "51.5074")
    monkeypatch.setenv("HOME_LON", "-0.1278")
    monkeypatch.setenv("OBSERVATORY_DB_PATH", str(_ensure_settings_loaded))
    s = Settings()
    monkeypatch.setattr(_config_mod, "settings", s)
    import observatory.api.routers.ingest as ingest_mod

    monkeypatch.setattr(ingest_mod, "settings", s, raising=False)

    app = FastAPI()
    app.include_router(ingest_router.router)
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture
def db_path(_ensure_settings_loaded: Path) -> Path:
    return _ensure_settings_loaded


def _make_payload(ts_iso: str | None = None) -> dict:
    """Create a valid Enviro Weather HTTP payload."""
    if ts_iso is None:
        ts_iso = "2026-06-08T12:34:56Z"
    return {
        "nickname": "observatory-weather",
        "model": "Enviro Weather",
        "uid": "e6614104035b2823",
        "timestamp": ts_iso,
        "readings": {
            "temperature": 18.5,
            "humidity": 72.0,
            "pressure": 1012.3,
            "luminance": 245.0,
            "voltage": None,
        },
    }


def test_ingest_success(client_with_auth: TestClient, db_path: Path) -> None:
    """Valid payload + correct basic auth → 201 and row appears in weather table."""
    payload = _make_payload("2026-06-08T12:34:56Z")
    resp = client_with_auth.post(
        "/ingest",
        json=payload,
        auth=("enviro", "test-secret-123"),
    )
    assert resp.status_code in (200, 201), f"Expected 2xx, got {resp.status_code}: {resp.text}"

    # Verify row in DB
    conn = sqlite3.connect(str(db_path))
    count = conn.execute("SELECT COUNT(*) FROM weather").fetchone()[0]
    conn.close()
    assert count >= 1, "Expected at least 1 weather row after successful ingest"


def test_ingest_dedup(client_with_auth: TestClient, db_path: Path) -> None:
    """Posting the same payload twice → 2xx both times, row count unchanged on second."""
    payload = _make_payload("2026-06-08T13:00:00Z")

    r1 = client_with_auth.post("/ingest", json=payload, auth=("enviro", "test-secret-123"))
    assert r1.status_code in (200, 201)

    conn = sqlite3.connect(str(db_path))
    count_after_first = conn.execute("SELECT COUNT(*) FROM weather").fetchone()[0]
    conn.close()

    r2 = client_with_auth.post("/ingest", json=payload, auth=("enviro", "test-secret-123"))
    assert r2.status_code in (200, 201, 202)

    conn = sqlite3.connect(str(db_path))
    count_after_second = conn.execute("SELECT COUNT(*) FROM weather").fetchone()[0]
    conn.close()

    assert count_after_second == count_after_first, (
        f"Duplicate ingest should not add row; "
        f"before={count_after_first}, after={count_after_second}"
    )


def test_ingest_unauth(client_with_auth: TestClient) -> None:
    """POST without credentials → 401."""
    payload = _make_payload()
    resp = client_with_auth.post("/ingest", json=payload)
    assert resp.status_code == 401


def test_ingest_wrong_password(client_with_auth: TestClient) -> None:
    """POST with wrong password → 401."""
    payload = _make_payload()
    resp = client_with_auth.post("/ingest", json=payload, auth=("enviro", "wrong-password"))
    assert resp.status_code == 401
