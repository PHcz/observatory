"""Regression test for the uvicorn attributes ``observatory.api.__main__`` relies on.

The service entrypoint fires ``sd_notify("READY=1")`` only once
``uvicorn.Server.started`` flips true, and shuts down by setting
``server.should_exit = True`` so in-flight requests drain. Both attributes are
undocumented; the entrypoint's docstring records them as "stable across uvicorn
0.32 to 0.39", which was an assertion nobody could check.

This test makes that claim executable. If a future uvicorn changes the
contract, it fails here — loudly, in the suite — instead of on the Pi, where
the only symptom is systemd timing out because READY=1 never arrives and
obs-api is restart-looped.

Every wait is bounded: a broken contract must FAIL the test, never hang it.
"""

from __future__ import annotations

import asyncio
from typing import Any

import uvicorn

# Generous enough for a loaded CI box, short enough to fail fast.
_STARTUP_TIMEOUT_SEC = 15.0
_SHUTDOWN_TIMEOUT_SEC = 15.0
_POLL_SEC = 0.02


async def _app(scope: dict[str, Any], receive: Any, send: Any) -> None:
    """Minimal ASGI app — enough for uvicorn to complete a real startup."""
    if scope["type"] == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return
    else:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


def _config() -> uvicorn.Config:
    # port=0 → ephemeral port, so the test never collides with a real service.
    return uvicorn.Config(
        app=_app,
        host="127.0.0.1",
        port=0,
        log_level="warning",
        access_log=False,
        lifespan="on",
    )


def test_server_exposes_started_and_should_exit() -> None:
    """Both attributes must exist and start False — __main__ polls them as bools."""
    server = uvicorn.Server(_config())
    assert server.started is False, "uvicorn.Server.started missing or not False at init"
    assert server.should_exit is False, "uvicorn.Server.should_exit missing or not False"


async def test_started_flips_true_and_should_exit_stops_serving() -> None:
    """The real contract: started goes true once serving, should_exit ends serve()."""
    server = uvicorn.Server(_config())
    serve_task = asyncio.create_task(server.serve())
    try:
        async with asyncio.timeout(_STARTUP_TIMEOUT_SEC):
            while not server.started:
                # If serve() died early, surface that instead of spinning.
                if serve_task.done():
                    await serve_task
                    raise AssertionError("serve() returned before started flipped true")
                await asyncio.sleep(_POLL_SEC)
        assert server.started is True

        # __main__'s SIGTERM path: flip should_exit and expect a clean return.
        server.should_exit = True
        await asyncio.wait_for(serve_task, timeout=_SHUTDOWN_TIMEOUT_SEC)
        assert serve_task.done()
    finally:
        if not serve_task.done():
            server.should_exit = True
            serve_task.cancel()
            await asyncio.gather(serve_task, return_exceptions=True)
