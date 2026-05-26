"""Phase 6 — tests for GET /api/aurora/current endpoint.

Plan 06-04 TDD RED phase. Tests use a local FastAPI app with the aurora
router mounted in isolation.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from observatory.api.routers import aurora as aurora_router


@pytest.fixture
def client(_ensure_settings_loaded: Path) -> TestClient:
    """Isolated FastAPI app with only the aurora router mounted."""
    app = FastAPI()
    app.include_router(aurora_router.router, prefix="/api")
    return TestClient(app)


@pytest.fixture
def db_path(_ensure_settings_loaded: Path) -> Path:
    return _ensure_settings_loaded


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_aurora(
    conn: sqlite3.Connection,
    ts: int,
    status: str = "green",
    detail: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO aurora_status (ts, status, detail) VALUES (?, ?, ?)",
        (ts, status, detail),
    )


# ---------------------------------------------------------------------------
# Empty DB -> 404
# ---------------------------------------------------------------------------


def test_empty_db_returns_404(client: TestClient) -> None:
    resp = client.get("/api/aurora/current")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Returns latest row by ts DESC (not by id)
# ---------------------------------------------------------------------------


def test_returns_latest_row(client: TestClient, db_path: Path) -> None:
    now = int(time.time())
    conn = sqlite3.connect(str(db_path))
    _insert_aurora(conn, now - 300, status="green")
    _insert_aurora(conn, now - 100, status="amber")  # latest
    _insert_aurora(conn, now - 200, status="yellow")
    conn.commit()
    conn.close()

    resp = client.get("/api/aurora/current")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "amber"
    assert body["ts"] == now - 100


# ---------------------------------------------------------------------------
# detail field: None and non-None both work
# ---------------------------------------------------------------------------


def test_detail_none(client: TestClient, db_path: Path) -> None:
    now = int(time.time())
    conn = sqlite3.connect(str(db_path))
    _insert_aurora(conn, now - 50, status="green", detail=None)
    conn.commit()
    conn.close()

    resp = client.get("/api/aurora/current")
    assert resp.status_code == 200
    body = resp.json()
    assert body["detail"] is None


def test_detail_present(client: TestClient, db_path: Path) -> None:
    now = int(time.time())
    conn = sqlite3.connect(str(db_path))
    _insert_aurora(conn, now - 50, status="red", detail="AWN:VAL:yo123")
    conn.commit()
    conn.close()

    resp = client.get("/api/aurora/current")
    assert resp.status_code == 200
    body = resp.json()
    assert body["detail"] == "AWN:VAL:yo123"


# ---------------------------------------------------------------------------
# Response shape
# ---------------------------------------------------------------------------


def test_response_shape(client: TestClient, db_path: Path) -> None:
    now = int(time.time())
    conn = sqlite3.connect(str(db_path))
    _insert_aurora(conn, now - 50)
    conn.commit()
    conn.close()

    resp = client.get("/api/aurora/current")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"ts", "status", "detail"}
