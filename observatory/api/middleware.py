"""Phase 6 — Origin-header allowlist middleware. Populated by Plan 06-02."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class OriginAllowlistMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        raise NotImplementedError("Plan 06-02 implements")
