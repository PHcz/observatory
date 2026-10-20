"""Phase 6 Plan 06-02 — Origin-header allowlist middleware.

Mounted by Plan 06-07 into main.py via ``app.add_middleware(OriginAllowlistMiddleware)``.

Security model (SEC-04):
- Requests with NO Origin header pass through (curl, healthcheck, server-to-server).
- Requests with an Origin whose hostname is in the RFC1918 CIDRs or listed hostnames are allowed.
- Everything else → 403 + structured WARNING log.

The allowlist is parsed once at middleware instantiation from
``settings.api_origin_allowlist`` (comma-separated string of CIDRs and bare
hostnames). Ports in the Origin URL are stripped before matching — only the
hostname matters.
"""

from __future__ import annotations

import functools
import ipaddress
import urllib.parse
from collections.abc import Awaitable, Callable

import structlog
from starlette.datastructures import Headers
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

log = structlog.get_logger(__name__)

_Network = ipaddress.IPv4Network | ipaddress.IPv6Network


def parse_allowlist(raw: str) -> tuple[list[_Network], set[str]]:
    """Parse a comma-separated allowlist string into networks and hostnames.

    Args:
        raw: Comma-separated string of IPv4/IPv6 CIDRs (``192.168.0.0/16``,
             ``fe80::/10``) and bare hostnames (``localhost``, ``observatory.local``).

    Returns:
        Tuple of (networks, hostnames) where networks is a list of
        ``IPv4Network``/``IPv6Network`` objects and hostnames is a lowercased set.
    """
    networks: list[_Network] = []
    hostnames: set[str] = set()

    if not raw.strip():
        return networks, hostnames

    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        try:
            # IPv6 is kept: the API is dual-stack since 2026-10-07, and an IPv6
            # entry used to be dropped here without a word (security audit C7).
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            # Not a valid CIDR or bare IP — treat as a hostname string.
            hostnames.add(entry.lower())

    return networks, hostnames


@functools.lru_cache(maxsize=8)
def _parsed(raw: str) -> tuple[list[_Network], set[str]]:
    """parse_allowlist, memoised: the Host check runs on every request."""
    return parse_allowlist(raw)


def hostname_allowed(
    hostname: str,
    networks: list[_Network],
    hostnames: set[str],
) -> bool:
    """Return True if hostname matches any allowlisted network or hostname."""
    hostname_lower = hostname.lower()
    try:
        addr = ipaddress.ip_address(hostname_lower)
        for network in networks:
            if addr in network:
                return True
    except ValueError:
        pass
    # Exact hostname match only -- "observatory.local.attacker.com" must not pass.
    return hostname_lower in hostnames


def is_origin_allowed(origin: str | None, allowlist_raw: str) -> bool:
    """The Origin decision, shared by the HTTP middleware and the /ws router.

    It has to be callable from the router because OriginAllowlistMiddleware is a
    BaseHTTPMiddleware, which Starlette never runs for `websocket` scope. Before
    this existed, /ws accepted any Origin -- security audit 2026-10-20, H1.

    - No Origin header -> allowed (non-browser clients: scripts, probes).
    - Unparseable Origin, or one with no hostname (e.g. the literal "null" that
      sandboxed iframes send) -> denied.
    - Otherwise allowed only if the hostname matches the allowlist.
    """
    if origin is None:
        return True
    try:
        hostname = urllib.parse.urlparse(origin).hostname
    except ValueError:
        return False
    if not hostname:
        return False
    networks, hostnames = _parsed(allowlist_raw)
    return hostname_allowed(hostname, networks, hostnames)


class OriginAllowlistMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that 403s cross-origin requests not in the LAN allowlist.

    Constructor args:
        app: The ASGI application.
        allowlist_raw: Optional raw allowlist string. If ``None`` (default),
            reads ``settings.api_origin_allowlist`` at instantiation. Passing
            an explicit string is useful in tests to avoid importing settings.
    """

    def __init__(self, app: ASGIApp, allowlist_raw: str | None = None) -> None:
        super().__init__(app)
        if allowlist_raw is None:
            from observatory.config import settings

            allowlist_raw = settings.api_origin_allowlist
        self._allowed_networks, self._allowed_hostnames = parse_allowlist(allowlist_raw or "")

    def _is_allowed(self, hostname: str) -> bool:
        """Return True if hostname matches any network or hostname in the allowlist."""
        return hostname_allowed(hostname, self._allowed_networks, self._allowed_hostnames)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        origin = request.headers.get("origin")

        # No Origin header → operator-facing / server-to-server → pass through.
        if origin is None:
            return await call_next(request)

        # Parse the Origin URL to extract hostname.
        try:
            parsed = urllib.parse.urlparse(origin)
            hostname: str | None = parsed.hostname  # Returns lowercased hostname or None.
        except Exception:
            hostname = None

        if not hostname:
            log.warning(
                "origin_rejected_unparseable",
                origin=origin,
                client_host=getattr(request.client, "host", "unknown"),
            )
            return Response(
                status_code=403,
                content='{"detail":"Origin not allowed"}',
                media_type="application/json",
            )

        if self._is_allowed(hostname):
            return await call_next(request)

        # Rejected — log and return 403.
        log.warning(
            "origin_rejected",
            origin=origin,
            client_host=getattr(request.client, "host", "unknown"),
        )
        return Response(
            status_code=403,
            content='{"detail":"Origin not allowed"}',
            media_type="application/json",
        )


def is_host_allowed(host: str | None, allowlist_raw: str) -> bool:
    """True if a Host header names this LAN service (port and IPv6 brackets ok).

    A missing Host header passes: browsers always send one, so its absence
    cannot be a DNS-rebinding request. A zone-ID literal (``[fe80::1%en0]``) is
    rejected; browsers never send those either.
    """
    if host is None:
        return True
    try:
        hostname = urllib.parse.urlsplit(f"//{host}").hostname
    except ValueError:
        return False
    if not hostname:
        return False
    networks, hostnames = _parsed(allowlist_raw)
    return hostname_allowed(hostname, networks, hostnames)


class HostAllowlistMiddleware:
    """Reject HTTP and WebSocket requests whose Host is not this LAN service.

    Defends against DNS rebinding: a hostile page whose own domain re-resolves
    to the Pi still sends ``Host: <hostile domain>``. Deliberately pure ASGI
    rather than BaseHTTPMiddleware -- Starlette never runs BaseHTTPMiddleware
    for websocket scope, which is exactly how /ws went unprotected (audit H1).
    """

    def __init__(self, app: ASGIApp, allowlist_raw: str | None = None) -> None:
        self.app = app
        self._allowlist_raw = allowlist_raw

    def _allowlist(self) -> str:
        if self._allowlist_raw is not None:
            return self._allowlist_raw
        from observatory.config import settings

        return settings.api_origin_allowlist if settings is not None else ""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        hosts = Headers(scope=scope).getlist("host")
        # RFC 9112 s3.2: more than one Host header MUST be rejected -- "which one
        # wins" differs between proxies and servers, the root of smuggling bugs.
        host = hosts[0] if len(hosts) == 1 else None
        if len(hosts) <= 1 and is_host_allowed(host, self._allowlist()):
            await self.app(scope, receive, send)
            return
        client = scope.get("client")
        log.warning("host_rejected", host=host, client_host=client[0] if client else "unknown")
        if scope["type"] == "websocket":
            await receive()  # consume websocket.connect
            await send({"type": "websocket.close", "code": 1008})
            return
        await PlainTextResponse("Invalid host header", status_code=400)(scope, receive, send)
