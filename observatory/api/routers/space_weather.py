"""Phase 6 — /api/space-weather endpoints. Populated by Plan 06-03 and 06-04."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/space-weather")
def get_space_weather() -> dict:  # type: ignore[type-arg]
    raise NotImplementedError("Plan 06-03 implements")


@router.get("/space-weather/current")
def get_space_weather_current() -> dict:  # type: ignore[type-arg]
    raise NotImplementedError("Plan 06-04 implements")
