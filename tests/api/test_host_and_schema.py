"""Host-header allowlist, hidden API schema, IPv6 in the LAN allowlist.

Security audit 2026-10-20: M11 (no foreign-Host test), F03/F57/F71
(/openapi.json served in production), C7 (allowlist silently dropped IPv6
CIDRs, stale since the API went dual-stack).

The Host check defends against DNS rebinding: a hostile page whose own domain
re-resolves to 192.168.0.75 still sends `Host: <hostile domain>`. The Hub
currently filters such DNS answers, so this is defence in depth -- but it must
cover websockets too, or it repeats the original /ws hole.
"""

from __future__ import annotations

import ipaddress

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from observatory.api.middleware import is_origin_allowed, parse_allowlist

DEFAULT_ALLOWLIST = (
    "192.168.0.0/16,10.0.0.0/8,172.16.0.0/12,localhost,127.0.0.1,observatory.local,::1,fe80::/10"
)


@pytest.fixture
def client() -> TestClient:
    from observatory.api.main import app

    return TestClient(app)


@pytest.mark.parametrize("host", ["evil.example.com", "evil.example.com:8000", "8.8.8.8:8000"])
def test_foreign_host_rejected(client: TestClient, host: str) -> None:
    assert client.get("/api/health", headers={"host": host}).status_code == 400


@pytest.mark.parametrize(
    "host",
    [
        "observatory.local:8000",
        "observatory.local",
        "192.168.0.75:8000",
        "localhost:5173",
        "127.0.0.1:8000",
        "[::1]:8000",
        "[fe80::feb:e023:9a05:975f]:8000",
    ],
)
def test_lan_hosts_allowed(client: TestClient, host: str) -> None:
    assert client.get("/api/health", headers={"host": host}).status_code != 400


def test_foreign_host_rejected_on_websocket_too(client: TestClient) -> None:
    """A Host check that only covers HTTP would repeat the original /ws hole."""
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws", headers={"host": "evil.example.com"}) as ws:
            ws.receive_json()


def test_openapi_schema_not_served_in_production(client: TestClient) -> None:
    """docs_url was gated and redoc_url nulled, but openapi_url never was."""
    assert client.get("/openapi.json", headers={"host": "localhost"}).status_code == 404


def test_allowlist_keeps_ipv6_networks() -> None:
    networks, _ = parse_allowlist("192.168.0.0/16,fe80::/10,localhost")
    assert ipaddress.ip_network("fe80::/10") in networks, "IPv6 CIDRs were silently dropped"


def test_ipv6_link_local_origin_allowed_by_default() -> None:
    from observatory.config import Settings

    default = Settings.model_fields["api_origin_allowlist"].default
    assert is_origin_allowed("http://[fe80::1]:8000", default)
    assert not is_origin_allowed("http://[2001:db8::1]:8000", default)


def test_duplicate_host_headers_rejected() -> None:
    """RFC 9112 s3.2: a request with more than one Host header MUST get a 400.

    Found while verifying live: the `websockets` client library adds a second
    Host rather than replacing its own, and the check silently used the first.
    Browsers never send two, so this is hardening -- but "which Host wins"
    differs between proxies and servers, which is how smuggling bugs start.
    """
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route

    from observatory.api.middleware import HostAllowlistMiddleware

    inner = Starlette(routes=[Route("/", lambda r: PlainTextResponse("ok"))])
    mw = HostAllowlistMiddleware(inner, allowlist_raw=DEFAULT_ALLOWLIST)

    sent: list[dict[str, object]] = []

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    import asyncio

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": [(b"host", b"observatory.local:8000"), (b"host", b"evil.example.com")],
        "client": ("192.168.0.95", 5000),
        "server": ("192.168.0.75", 8000),
        "scheme": "http",
        "http_version": "1.1",
        "root_path": "",
    }
    asyncio.run(mw(scope, receive, send))  # type: ignore[arg-type]
    start = next(m for m in sent if m["type"] == "http.response.start")
    assert start["status"] == 400
