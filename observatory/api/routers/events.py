"""Phase 6 — /api/events endpoints. Populated by Plan 06-04."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/events/recent")
def get_events_recent() -> dict:  # type: ignore[type-arg]
    raise NotImplementedError("Plan 06-04 implements")
