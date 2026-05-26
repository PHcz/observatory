"""Phase 6 — /api/stats endpoints. Populated by Plan 06-04."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/stats/today")
def get_stats_today() -> dict:  # type: ignore[type-arg]
    raise NotImplementedError("Plan 06-04 implements")
