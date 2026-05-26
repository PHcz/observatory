"""Phase 6 Plan 06-02 — Tests for OriginAllowlistMiddleware and parse_allowlist."""

from __future__ import annotations

import pytest
import structlog.testing
from fastapi import FastAPI
from fastapi.testclient import TestClient

from observatory.api.middleware import OriginAllowlistMiddleware, parse_allowlist


@pytest.fixture
def mw_client() -> TestClient:
    app = FastAPI()

    @app.get("/ping")
    def ping() -> dict[str, bool]:
        return {"ok": True}

    app.add_middleware(OriginAllowlistMiddleware)
    return TestClient(app)


# --- No Origin header (curl, healthcheck, server-to-server) ---


def test_no_origin_passes(mw_client: TestClient) -> None:
    resp = mw_client.get("/ping")
    assert resp.status_code == 200


# --- RFC1918 IPs allowed ---


def test_rfc1918_192_168_allowed(mw_client: TestClient) -> None:
    resp = mw_client.get("/ping", headers={"Origin": "http://192.168.1.100"})
    assert resp.status_code == 200


def test_rfc1918_10_x_allowed(mw_client: TestClient) -> None:
    resp = mw_client.get("/ping", headers={"Origin": "http://10.0.5.200:3000"})
    assert resp.status_code == 200


def test_rfc1918_172_16_allowed(mw_client: TestClient) -> None:
    resp = mw_client.get("/ping", headers={"Origin": "http://172.16.5.1"})
    assert resp.status_code == 200


# --- Listed hostnames allowed ---


def test_localhost_allowed(mw_client: TestClient) -> None:
    resp = mw_client.get("/ping", headers={"Origin": "http://localhost:5173"})
    assert resp.status_code == 200


def test_127_0_0_1_allowed(mw_client: TestClient) -> None:
    resp = mw_client.get("/ping", headers={"Origin": "http://127.0.0.1:8000"})
    assert resp.status_code == 200


def test_observatory_local_allowed(mw_client: TestClient) -> None:
    resp = mw_client.get("/ping", headers={"Origin": "http://observatory.local"})
    assert resp.status_code == 200


def test_observatory_local_with_port_allowed(mw_client: TestClient) -> None:
    """Port suffix stripped — only hostname is matched."""
    resp = mw_client.get("/ping", headers={"Origin": "http://observatory.local:8000"})
    assert resp.status_code == 200


# --- Rejected origins ---


def test_external_hostname_rejected(mw_client: TestClient) -> None:
    resp = mw_client.get("/ping", headers={"Origin": "http://evil.example.com"})
    assert resp.status_code == 403
    assert resp.json() == {"detail": "Origin not allowed"}


def test_public_ip_rejected(mw_client: TestClient) -> None:
    resp = mw_client.get("/ping", headers={"Origin": "http://8.8.8.8"})
    assert resp.status_code == 403


def test_malformed_ip_rejected(mw_client: TestClient) -> None:
    """Hostname that looks like an IP but is invalid is treated as hostname string."""
    resp = mw_client.get("/ping", headers={"Origin": "http://192.168.1.1.bad"})
    assert resp.status_code == 403


def test_not_a_url_rejected(mw_client: TestClient) -> None:
    """Unparseable origin (no scheme, no hostname) → 403."""
    resp = mw_client.get("/ping", headers={"Origin": "not a url"})
    assert resp.status_code == 403


# --- parse_allowlist helper ---


def test_parse_allowlist_mixed() -> None:
    networks, hosts = parse_allowlist("192.168.0.0/16,localhost,10.0.0.0/8")
    assert len(networks) == 2
    assert hosts == {"localhost"}


def test_parse_allowlist_empty() -> None:
    networks, hosts = parse_allowlist("")
    assert networks == []
    assert hosts == set()


# --- Structured log on rejection ---


def test_rejection_emits_origin_rejected_log(mw_client: TestClient) -> None:
    with structlog.testing.capture_logs() as cap:
        resp = mw_client.get("/ping", headers={"Origin": "http://evil.example.com"})
    assert resp.status_code == 403
    events = [e for e in cap if e.get("event") == "origin_rejected"]
    assert events, f"Expected 'origin_rejected' log entry, got: {cap}"
    assert "evil.example.com" in str(events[0].get("origin", ""))
