"""Phase 6 — /api/earthquakes endpoints. Populated by Plan 06-04."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/earthquakes")
def get_earthquakes() -> dict:  # type: ignore[type-arg]
    raise NotImplementedError("Plan 06-04 implements")
