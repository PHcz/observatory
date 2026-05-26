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
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from observatory.api.db_watcher import db_watcher_loop
from observatory.api.middleware import OriginAllowlistMiddleware
from observatory.api.routers import aurora as aurora_router
from observatory.api.routers import current as current_router
from observatory.api.routers import earthquakes as earthquakes_router
from observatory.api.routers import events as events_router
from observatory.api.routers import health as health_router
from observatory.api.routers import lightning as lightning_router
from observatory.api.routers import muon as muon_router
from observatory.api.routers import space_weather as space_weather_router
from observatory.api.routers import stats as stats_router
from observatory.api.routers import weather as weather_router
from observatory.api.routers import ws as ws_router
from observatory.config import settings

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    log.info("api_lifespan_starting")
    task = asyncio.create_task(db_watcher_loop())
    try:
        yield
    finally:
        log.info("api_lifespan_stopping")
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


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
app.include_router(ws_router.router, tags=["ws"])  # no /api prefix

# StaticFiles LAST. Skip if bundle dir absent (dev/CI without built frontend).
_bundle_dir = Path(settings.api_static_bundle_dir if settings is not None else "")
if _bundle_dir.exists() and _bundle_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(_bundle_dir), html=True), name="frontend")
    log.info("static_bundle_mounted", path=str(_bundle_dir))
else:
    log.warning("static_bundle_missing", path=str(_bundle_dir))
