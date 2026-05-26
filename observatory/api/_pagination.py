"""Phase 6 — cursor-based pagination helper. Populated by Plan 06-01."""

from __future__ import annotations


def resolve_before_ts(before_ts: int | None, default_to: int) -> int:
    """Return effective upper-bound timestamp for list/page queries."""
    raise NotImplementedError("Plan 06-01 implements")
