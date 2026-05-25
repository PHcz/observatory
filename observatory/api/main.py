"""FastAPI app — Phase 5 minimum scaffold. Plan 05-05 fills out /api/health."""

from __future__ import annotations

from fastapi import FastAPI

from observatory.api.routers import health as health_router

app = FastAPI(
    title="Observatory API",
    version="0.1.0",
    description="Local home observatory — Phase 5 scaffold (health endpoint only)",
)
app.include_router(health_router.router, prefix="/api", tags=["health"])
