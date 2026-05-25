"""/api/health endpoint — Phase 5 plan 05-05 implements the real body."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict[str, object]:
    """Stub; 05-05 replaces with real health-check payload."""
    return {"status": "stub", "timestamp": 0}
