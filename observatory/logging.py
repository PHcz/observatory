"""Structured JSON logging via structlog. Call configure_logging() at service start."""

from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(level: str = "INFO") -> None:
    """Configure structlog to emit JSON to stdout. Call once per process at startup."""
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper()),
    )
    # httpx logs `HTTP Request: <METHOD> <URL>` at INFO, and secrets live in
    # URLs here: the Telegram bot token, the ntfy topic, and the home
    # coordinates in Open-Meteo queries. At an INFO root they reached the
    # journal on every alert and poll (security audit 2026-10-20, M1/M2).
    # Only warnings and errors from the HTTP stack are worth keeping.
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level.upper())),
        cache_logger_on_first_use=True,
    )
