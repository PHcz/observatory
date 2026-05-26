"""Service entrypoint: python -m observatory.api.

Launches uvicorn programmatically so we can fire ``sd_notify("READY=1")``
AFTER ``uvicorn.Server.started`` flips true (uvicorn does not signal systemd
natively). A watcher coroutine then pings ``WATCHDOG=1`` every
``settings.api_watchdog_ping_interval_sec`` (default 10s) — the unit file pins
``WatchdogSec=30s`` so two missed pings trip a restart.

SIGTERM/SIGINT: notifier sends ``STOPPING=1`` and we set
``server.should_exit=True`` so uvicorn drains in flight requests and runs the
ASGI lifespan shutdown.

The ``server.started`` flag is undocumented-but-stable across uvicorn 0.32 to
0.39 (the pin range locked in Plan 05-00). If uvicorn changes the contract,
the watcher will simply never send READY=1 and systemd will time out — failure
mode is loud, not silent.
"""

from __future__ import annotations

import asyncio
import signal
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


async def _serve() -> None:
    notifier = sdnotify.SystemdNotifier()
    config = uvicorn.Config(
        app=app,
        host=settings.api_bind_host,
        port=settings.api_bind_port,
        log_level="info",
        access_log=False,
        lifespan="on",
    )
    server = uvicorn.Server(config)

    async def _ready_then_watchdog() -> None:
        # Wait for uvicorn to start serving before we tell systemd READY.
        while not server.started and not server.should_exit:
            await asyncio.sleep(READY_POLL_INTERVAL_SEC)
        if server.should_exit:
            return
        notifier.notify("READY=1")
        log.info(
            "api_ready",
            host=settings.api_bind_host,
            port=settings.api_bind_port,
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
        await server.serve()
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
