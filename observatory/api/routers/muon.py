"""Phase 6 — /api/muon endpoints. Populated by Plan 06-03."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/muon")
def get_muon() -> dict:  # type: ignore[type-arg]
    raise NotImplementedError("Plan 06-03 implements")
