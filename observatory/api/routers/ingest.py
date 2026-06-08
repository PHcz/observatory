"""Phase 16 ENH-06 — POST /ingest HTTP fallback endpoint.

Accepts the Pimoroni Enviro Weather custom-HTTP payload, validates it with the
existing pydantic models, and writes to SQLite via the existing dedup writer.
This route is a FALLBACK for MQTT outages — MQTT remains primary.

The Enviro custom-HTTP payload is identical in shape to the MQTT envelope already
parsed by ``observatory.weather.payload.parse_envelope``. No custom insert logic
is needed: ``write_reading()`` already handles UNIQUE(node_id, ts) deduplication.

Security:
- HTTP Basic Auth is required. The password lives only in Pi .env and is never
  committed (empty password blocks all ingests fail-closed in production).
- The route is registered WITHOUT the /api prefix (like /ws) because the
  Pimoroni board posts to a bare path.

Returns:
- 201: accepted and written (or deduplicated — 2xx clears the board cache).
- 401: missing or incorrect credentials.
- 422: invalid payload (ValidationError from parse_envelope).
"""

from __future__ import annotations

import secrets

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import ValidationError

from observatory.config import settings
from observatory.weather.payload import parse_envelope
from observatory.weather.writer import write_reading

log = structlog.get_logger(__name__)

router = APIRouter()
security = HTTPBasic()


@router.post("/ingest", status_code=201)
async def post_ingest(
    request: Request,
    credentials: HTTPBasicCredentials = Depends(security),  # noqa: B008
) -> dict:
    """Accept an Enviro Weather HTTP payload and write it to SQLite.

    Validates with existing pydantic WeatherEnvelope model and writes via
    write_reading() which has UNIQUE(node_id, ts) dedup — safe for board
    replays. Returns 201 so the Enviro board clears its local upload cache.

    Auth: HTTP Basic (user = settings.observatory_ingest_basic_auth_user,
          password = settings.observatory_ingest_basic_auth_password).
          Empty password blocks all ingests fail-closed.
    """
    # Constant-time comparison to prevent timing attacks.
    # Empty password always fails (fail-closed).
    user_ok = secrets.compare_digest(
        credentials.username,
        settings.observatory_ingest_basic_auth_user,
    )
    pass_ok = bool(settings.observatory_ingest_basic_auth_password) and secrets.compare_digest(
        credentials.password,
        settings.observatory_ingest_basic_auth_password,
    )
    if not (user_ok and pass_ok):
        log.warning("ingest_auth_failed", username=credentials.username)
        raise HTTPException(status_code=401, detail="Unauthorized")

    body = await request.body()
    try:
        envelope = parse_envelope(body)
    except (ValidationError, ValueError) as exc:
        log.warning("ingest_parse_error", error=str(exc))
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    write_reading(envelope)  # dedup on UNIQUE(node_id, ts) handles replays
    log.info("ingest_accepted", node_id=envelope.nickname)
    return {"status": "accepted"}
