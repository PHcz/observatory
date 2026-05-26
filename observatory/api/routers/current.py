"""Phase 6 — /api/current endpoints. Populated by Plan 06-05."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/current")
def get_current() -> dict:  # type: ignore[type-arg]
    raise NotImplementedError("Plan 06-05 implements")
