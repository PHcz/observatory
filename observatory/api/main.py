"""FastAPI app — Phase 6 full wiring.

Lifespan starts the db_watcher background task; ASGI middleware enforces
Origin allowlist; 10 routers expose REST + WebSocket; StaticFiles serves
the SvelteKit bundle at /. /docs is gated on OBS_ENV.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from observatory.api.db_watcher import db_watcher_loop
from observatory.api.middleware import OriginAllowlistMiddleware
from observatory.api.routers import air_quality as air_quality_router
from observatory.api.routers import aurora as aurora_router
from observatory.api.routers import current as current_router
from observatory.api.routers import earthquakes as earthquakes_router
from observatory.api.routers import events as events_router
from observatory.api.routers import forbush as forbush_router
from observatory.api.routers import forecast as forecast_router
from observatory.api.routers import health as health_router
from observatory.api.routers import lightning as lightning_router
from observatory.api.routers import muon as muon_router
from observatory.api.routers import nmdb as nmdb_router
from observatory.api.routers import space_weather as space_weather_router
from observatory.api.routers import stats as stats_router
from observatory.api.routers import weather as weather_router
from observatory.api.routers import ws as ws_router
from observatory.config import settings
from observatory.weather.subscriber import run_subscriber

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    log.info("api_lifespan_starting")
    stop_event = asyncio.Event()
    db_task = asyncio.create_task(db_watcher_loop(), name="db_watcher")
    subscriber_task = asyncio.create_task(run_subscriber(stop_event), name="weather_subscriber")
    try:
        yield
    finally:
        log.info("api_lifespan_stopping")
        stop_event.set()  # graceful signal to subscriber loop
        for t in (db_task, subscriber_task):
            t.cancel()
        for t in (db_task, subscriber_task):
            try:
                await t
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                log.warning("lifespan_task_exit_error", task=t.get_name(), error=str(exc))


_docs_url = "/docs" if (settings is not None and settings.obs_env == "development") else None

app = FastAPI(
    title="Observatory API",
    version="0.2.0",
    description="Local home observatory — Phase 6 API core + WebSocket",
    debug=False,
    docs_url=_docs_url,
    redoc_url=None,
    lifespan=lifespan,
)

# Middleware (added first → runs first on inbound).
app.add_middleware(OriginAllowlistMiddleware)


@app.middleware("http")
async def cache_control(request: Request, call_next):  # type: ignore[no-untyped-def]
    """Cache policy for the SPA bundle.

    Content-hashed assets (``/_app/immutable/*``) are immutable — cache them
    for a year. HTML shells and extensionless SPA routes (``/``, ``/settings``)
    and API responses MUST always revalidate (``no-cache``); otherwise a mobile
    browser can keep a stale ``200.html`` shell that references JS chunk hashes
    purged by the next ``rsync --delete`` deploy, leaving SvelteKit unable to
    import the route module → hard-nav fallback → white-screen reload loop.
    """
    response = await call_next(request)
    path = request.url.path
    last_segment = path.rsplit("/", 1)[-1]
    if path.startswith("/_app/immutable/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif path.endswith(".html") or "." not in last_segment:
        # HTML shell / extensionless route / API — never serve stale from cache.
        response.headers["Cache-Control"] = "no-cache"
    return response


# Routers — health (existing) + 9 new. WS uses no /api prefix.
app.include_router(health_router.router, prefix="/api", tags=["health"])
app.include_router(current_router.router, prefix="/api", tags=["current"])
app.include_router(weather_router.router, prefix="/api", tags=["weather"])
app.include_router(muon_router.router, prefix="/api", tags=["muon"])
app.include_router(earthquakes_router.router, prefix="/api", tags=["earthquakes"])
app.include_router(space_weather_router.router, prefix="/api", tags=["space_weather"])
app.include_router(lightning_router.router, prefix="/api", tags=["lightning"])
app.include_router(aurora_router.router, prefix="/api", tags=["aurora"])
app.include_router(events_router.router, prefix="/api", tags=["events"])
app.include_router(stats_router.router, prefix="/api", tags=["stats"])
app.include_router(forecast_router.router, prefix="/api", tags=["forecast"])
app.include_router(air_quality_router.router, prefix="/api", tags=["air_quality"])
app.include_router(nmdb_router.router, prefix="/api", tags=["nmdb"])
app.include_router(forbush_router.router, prefix="/api", tags=["forbush"])
app.include_router(ws_router.router, tags=["ws"])  # no /api prefix

# StaticFiles LAST. Skip if bundle dir absent (dev/CI without built frontend).
_bundle_dir = Path(settings.api_static_bundle_dir if settings is not None else "")
if _bundle_dir.exists() and _bundle_dir.is_dir():
    _spa_fallback = _bundle_dir / "200.html"

    @app.exception_handler(404)
    async def spa_fallback(request: Request, exc: object) -> FileResponse | JSONResponse:
        # /api/* and /ws/* return JSON 404; everything else falls back to 200.html
        # so /settings (and any future SvelteKit route) survives hard refresh.
        path = request.url.path
        if path.startswith("/api/") or path.startswith("/ws"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        if _spa_fallback.exists():
            return FileResponse(
                str(_spa_fallback),
                status_code=200,
                headers={"Cache-Control": "no-cache"},
            )
        return JSONResponse({"detail": "Not Found"}, status_code=404)

    app.mount("/", StaticFiles(directory=str(_bundle_dir), html=True), name="frontend")
    log.info("static_bundle_mounted", path=str(_bundle_dir))
else:
    log.warning("static_bundle_missing", path=str(_bundle_dir))
