"""Phase 6 — /api/lightning endpoints. Populated by Plan 06-04."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/lightning/summary")
def get_lightning_summary() -> dict:  # type: ignore[type-arg]
    raise NotImplementedError("Plan 06-04 implements")
