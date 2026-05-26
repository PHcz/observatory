"""Phase 6 — cursor-based pagination helper. Implemented by Plan 06-01."""

from __future__ import annotations

DEFAULT_LIMIT: int = 100
MAX_LIMIT: int = 1000


def resolve_before_ts(before_ts: int | None, default_to: int) -> int:
    """Return effective upper-bound timestamp for list/page queries.

    Returns `before_ts` if non-None, otherwise `default_to`.
    """
    return before_ts if before_ts is not None else default_to
