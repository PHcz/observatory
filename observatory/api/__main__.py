"""Service entrypoint: python -m observatory.api.

Launches uvicorn programmatically so we can fire ``sd_notify("READY=1")``
AFTER ``uvicorn.Server.started`` flips true (uvicorn does not signal systemd
natively). A watcher coroutine then pings ``WATCHDOG=1`` every
``settings.api_watchdog_ping_interval_sec`` (default 10s) — the unit file pins
``WatchdogSec=30s`` so two missed pings trip a restart.

SIGTERM/SIGINT: notifier sends ``STOPPING=1`` and we set
``server.should_exit=True`` so uvicorn drains in flight requests and runs the
ASGI lifespan shutdown.

The ``server.started`` and ``server.should_exit`` flags are undocumented. They
are pinned by ``tests/api/test_uvicorn_contract.py``, which starts a real
``uvicorn.Server`` on an ephemeral port and asserts ``started`` flips true and
``should_exit`` ends ``serve()``. That test — not the version bound — is what
keeps this safe across upgrades: if uvicorn changes the contract it fails in
the suite, rather than on the Pi where the only symptom is systemd timing out
because READY=1 never arrives.
"""

from __future__ import annotations

import asyncio
import signal
import socket
from typing import Final

import sdnotify
import structlog
import uvicorn

from observatory.api.main import app
from observatory.config import settings
from observatory.logging import configure_logging

log = structlog.get_logger(__name__)

# How often we poll uvicorn.Server.started before firing READY=1.
READY_POLL_INTERVAL_SEC: Final[float] = 0.05


def resolve_lan_ip() -> str:
    """Return the Pi's outbound LAN IPv4 address.

    Uses the standard "connect a UDP socket to a TEST-NET address" trick:
    no packets are actually sent (UDP is connectionless), but the kernel
    selects the outbound interface based on the routing table and binds
    the socket to that interface's IP. ``getsockname()`` then reveals it.

    This is robust against Debian's default /etc/hosts mapping
    (``hostname → 127.0.1.1``) which defeats the naive
    ``gethostname()+getaddrinfo()`` approach.

    Falls back to ``getaddrinfo()`` if the UDP trick fails (e.g. in CI
    sandboxes that block socket creation).

    Raises:
        RuntimeError: If no non-loopback IPv4 address can be determined.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # 192.0.2.0/24 is TEST-NET-1 (RFC 5737) — guaranteed unroutable,
        # no packets leave the host. Any non-loopback target works.
        sock.connect(("192.0.2.1", 1))
        addr = str(sock.getsockname()[0])
    except OSError:
        addr = ""
    finally:
        sock.close()

    if addr and not addr.startswith("127."):
        return addr

    # Fallback for test/CI environments where socket.connect is blocked.
    hostname = socket.gethostname()
    try:
        results = socket.getaddrinfo(hostname, None, socket.AF_INET)
    except OSError as exc:
        raise RuntimeError(
            f"Cannot resolve LAN IP via UDP-connect trick or getaddrinfo "
            f"for hostname {hostname!r}: {exc}"
        ) from exc
    for info in results:
        candidate = str(info[4][0])
        if not candidate.startswith("127."):
            return candidate
    raise RuntimeError(
        f"No non-loopback IPv4 found for hostname {hostname!r} "
        f"(UDP-connect trick also failed — host may have no LAN interface up)"
    )


def make_listen_socket(host: str, port: int, *, backlog: int) -> socket.socket | None:
    """Return a dual-stack listening socket for an IPv6 ``host``, else ``None``.

    ``observatory.local`` resolves to both the Pi's IPv4 address and its IPv6
    link-local address, because Avahi publishes A and AAAA records. A browser
    may pick either, so the API has to answer on both or it is intermittently
    "unreachable" depending on which family the client prefers.

    One socket can serve both families, but only if we build it ourselves:
    Linux defaults ``net.ipv6.bindv6only=0``, yet ``asyncio``'s own
    ``loop.create_server()`` explicitly sets ``IPV6_V6ONLY=1`` on sockets it
    creates, which is what uvicorn uses when given a plain ``host``. Clearing
    the option on a socket we own and handing it to uvicorn is the only way
    through. Pinned by ``tests/api/test_dual_stack_bind.py``.

    Dual-stack applies to the wildcard ``::`` (what production binds). For a
    specific IPv6 address Linux sets IPV6_V6ONLY itself at bind time -- IPv4
    traffic can never reach one -- so that socket is simply IPv6.

    Returns ``None`` for IPv4 hosts (including ``"auto"``), where uvicorn's
    own bind is already correct and needs no help.
    """
    if ":" not in host:
        return None
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        sock.bind((host, port))
        sock.listen(backlog)
        sock.setblocking(False)
    except OSError:
        sock.close()
        raise
    return sock


async def _serve() -> None:
    notifier = sdnotify.SystemdNotifier()

    # Resolve bind host — "auto" means detect the Pi's LAN IP dynamically.
    if settings.api_bind_host == "auto":
        try:
            bind_host = resolve_lan_ip()
        except RuntimeError as exc:
            log.error("api_lan_ip_detect_failed", error=str(exc))
            raise SystemExit(1) from exc
        log.info(
            "api_bind_host_resolved",
            resolved=bind_host,
            hostname=socket.gethostname(),
        )
    else:
        bind_host = settings.api_bind_host

    config = uvicorn.Config(
        app=app,
        host=bind_host,
        port=settings.api_bind_port,
        log_level="info",
        access_log=False,
        lifespan="on",
    )
    server = uvicorn.Server(config)

    # Dual-stack listener for IPv6 bind hosts; None means "let uvicorn bind".
    listen_sock = make_listen_socket(bind_host, settings.api_bind_port, backlog=config.backlog)

    async def _ready_then_watchdog() -> None:
        # Wait for uvicorn to start serving before we tell systemd READY.
        while not server.started and not server.should_exit:
            await asyncio.sleep(READY_POLL_INTERVAL_SEC)
        if server.should_exit:
            return
        notifier.notify("READY=1")
        log.info(
            "api_ready",
            host=bind_host,
            port=settings.api_bind_port,
            dual_stack=listen_sock is not None,
        )
        # Watchdog ping loop. WatchdogSec=30s in the unit; default ping=10s.
        while not server.should_exit:
            notifier.notify("WATCHDOG=1")
            await asyncio.sleep(settings.api_watchdog_ping_interval_sec)

    def _on_term() -> None:
        notifier.notify("STOPPING=1")
        log.info("api_stopping")
        server.should_exit = True

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _on_term)
        except (NotImplementedError, ValueError):
            # Off-main-thread (tests) or platform without signal support.
            pass

    watchdog_task = asyncio.create_task(_ready_then_watchdog())
    try:
        await server.serve(sockets=[listen_sock] if listen_sock else None)
    finally:
        watchdog_task.cancel()


def main() -> int:
    configure_logging()
    log.info(
        "api_starting",
        host=settings.api_bind_host,
        port=settings.api_bind_port,
    )
    asyncio.run(_serve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
