"""Browser security headers on every HTTP response (security audit F55).

No CSP, nosniff, Referrer-Policy or frame-ancestors were sent, so the dashboard
could be framed by any page and nothing limited where it loaded code from.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    from observatory.api.main import app

    return TestClient(app)


def _csp(client: TestClient, path: str = "/api/health", host: str = "testserver") -> dict[str, str]:
    resp = client.get(path, headers={"host": host})
    directives = {}
    for part in resp.headers["content-security-policy"].split(";"):
        name, _, value = part.strip().partition(" ")
        directives[name] = value
    return directives


@pytest.mark.parametrize("path", ["/api/health", "/api/current", "/does-not-exist"])
def test_basic_security_headers_on_every_response(client: TestClient, path: str) -> None:
    h = client.get(path).headers
    assert h["x-content-type-options"] == "nosniff"
    assert h["referrer-policy"] == "no-referrer"
    assert h["x-frame-options"] == "DENY"
    assert "content-security-policy" in h


def test_csp_forbids_framing_plugins_and_foreign_code(client: TestClient) -> None:
    d = _csp(client)
    assert d["frame-ancestors"] == "'none'"
    assert d["object-src"] == "'none'"
    assert d["base-uri"] == "'self'"
    assert d["default-src"] == "'self'"
    for directive in ("script-src", "style-src", "font-src", "img-src", "connect-src"):
        assert "http" not in d[directive].replace("'self'", ""), (
            f"{directive} must not allow remote origins: {d[directive]!r}"
        )


def test_csp_allows_the_websocket_to_this_host_only(client: TestClient) -> None:
    """'self' does not cover ws:// in every browser, so name this host exactly
    -- never a bare ws: scheme, which would allow any host."""
    sources = _csp(client, host="observatory.local:8000")["connect-src"].split()
    assert "ws://observatory.local:8000" in sources
    assert "ws:" not in sources and "wss:" not in sources


def test_fonts_are_self_hosted(client: TestClient) -> None:
    d = _csp(client)
    assert "fonts.googleapis.com" not in str(d) and "fonts.gstatic.com" not in str(d)
