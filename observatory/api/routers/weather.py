"""Phase 6 — /api/weather endpoints. Populated by Plan 06-03."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/weather")
def get_weather() -> dict:  # type: ignore[type-arg]
    raise NotImplementedError("Plan 06-03 implements")
