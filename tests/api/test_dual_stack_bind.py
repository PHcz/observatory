"""Pin the dual-stack listening socket for obs-api.

Why this exists: ``observatory.local`` resolves to BOTH the Pi's IPv4 address
and its IPv6 link-local address (Avahi publishes A and AAAA). A browser picks
either. Binding a single IPv4 address left IPv6 clients with a stalled
connection; binding ``::`` through uvicorn's normal path left IPv4 clients
refused, because ``asyncio.loop.create_server()`` sets ``IPV6_V6ONLY=1`` on
sockets it creates itself (CPython disables Linux's default dual-stack).

The only way to serve both families from one socket is to build it ourselves
with ``IPV6_V6ONLY=0`` and hand it to uvicorn. These tests fail if that
regresses — the production symptom is "dashboard unreachable" for whichever
family happens to lose.
"""

from __future__ import annotations

import socket

import pytest

from observatory.api.__main__ import make_listen_socket

_CONNECT_TIMEOUT_SEC = 2.0


def _try_connect(family: int, addr: tuple[str, int]) -> bool:
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.settimeout(_CONNECT_TIMEOUT_SEC)
    try:
        sock.connect(addr)
        return True
    except OSError:
        return False
    finally:
        sock.close()


@pytest.mark.parametrize("host", ["::", "::0"])
def test_wildcard_ipv6_host_yields_dual_stack_socket(host: str) -> None:
    """The wildcard -- what production binds -- must have V6ONLY cleared."""
    sock = make_listen_socket(host, 0, backlog=16)
    assert sock is not None, f"expected a socket for IPv6 host {host!r}"
    try:
        assert sock.family == socket.AF_INET6
        assert sock.getsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY) == 0, (
            "IPV6_V6ONLY must be 0 or IPv4 clients get ConnectionRefused"
        )
    finally:
        sock.close()


def test_specific_ipv6_host_yields_an_ipv6_socket() -> None:
    """A SPECIFIC IPv6 address is a plain IPv6 socket; dual-stack does not apply.

    Linux sets IPV6_V6ONLY itself when a socket binds a specific, non-mapped IPv6
    address -- correctly, as IPv4 traffic can never reach one. macOS does not, so
    this case used to assert V6ONLY == 0 and passed on the dev Mac for two weeks
    until the first Linux CI run failed it (2026-10-20). The Pi runs Linux and
    binds the wildcard, so production was never affected.
    """
    sock = make_listen_socket("::1", 0, backlog=16)
    assert sock is not None
    try:
        assert sock.family == socket.AF_INET6
    finally:
        sock.close()


@pytest.mark.parametrize("host", ["0.0.0.0", "127.0.0.1", "192.168.1.20", "auto"])
def test_ipv4_host_defers_to_uvicorn(host: str) -> None:
    """IPv4 hosts need no special handling — uvicorn's own bind is correct."""
    assert make_listen_socket(host, 0, backlog=16) is None


def test_wildcard_socket_accepts_both_families() -> None:
    """The real contract: one socket, both families actually connectable."""
    sock = make_listen_socket("::", 0, backlog=16)
    assert sock is not None
    try:
        port = sock.getsockname()[1]
        assert _try_connect(socket.AF_INET6, ("::1", port)), "IPv6 loopback refused"
        assert _try_connect(socket.AF_INET, ("127.0.0.1", port)), (
            "IPv4 loopback refused — the socket is v6-only"
        )
    finally:
        sock.close()
