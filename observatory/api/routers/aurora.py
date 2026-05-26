"""Phase 6 — /api/aurora endpoints. Populated by Plan 06-04."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/aurora/current")
def get_aurora_current() -> dict:  # type: ignore[type-arg]
    raise NotImplementedError("Plan 06-04 implements")
