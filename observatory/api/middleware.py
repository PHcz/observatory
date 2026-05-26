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

import ipaddress
import urllib.parse
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

log = structlog.get_logger(__name__)


def parse_allowlist(raw: str) -> tuple[list[ipaddress.IPv4Network], set[str]]:
    """Parse a comma-separated allowlist string into networks and hostnames.

    Args:
        raw: Comma-separated string of IPv4 CIDRs (``192.168.0.0/16``) and
             bare hostnames (``localhost``, ``observatory.local``).

    Returns:
        Tuple of (networks, hostnames) where networks is a list of
        ``IPv4Network`` objects and hostnames is a lowercased set of strings.
    """
    networks: list[ipaddress.IPv4Network] = []
    hostnames: set[str] = set()

    if not raw.strip():
        return networks, hostnames

    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        try:
            net = ipaddress.ip_network(entry, strict=False)
            if isinstance(net, ipaddress.IPv4Network):
                networks.append(net)
            # IPv6 networks are silently ignored — observatory is IPv4-only LAN.
        except ValueError:
            # Not a valid CIDR or bare IP — treat as a hostname string.
            hostnames.add(entry.lower())

    return networks, hostnames


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
        hostname_lower = hostname.lower()
        # Try to interpret as an IPv4 address first.
        try:
            addr = ipaddress.ip_address(hostname_lower)
            for network in self._allowed_networks:
                if addr in network:
                    return True
            # Fall through to hostname check if not in any network.
        except ValueError:
            pass
        # Hostname-string match (covers "localhost", "observatory.local", etc.)
        return hostname_lower in self._allowed_hostnames

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
