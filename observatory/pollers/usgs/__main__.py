"""USGS earthquake poller — systemd oneshot entry point.

Composition: fetch (hardened httpx) -> parse_usgs (per-item resilient)
-> compute_parse_outcome (threshold gate) -> write_events (dedup + audit).

Exit semantics (CONTEXT-locked):
  0 = success (incl. zero-events quiet period, incl. partial-parse under threshold)
  1 = hard failure (network exhausted, response hardening, structural
      parse, or per-item failure ratio over threshold)
"""

from __future__ import annotations

import json
import sys
import time

import structlog

from observatory.config import settings
from observatory.logging import configure_logging
from observatory.pollers._http import (
    CrossHostRedirect,
    ResponseTooLarge,
    RetriesExhausted,
    fetch,
)
from observatory.pollers._write import compute_parse_outcome, write_events
from observatory.pollers.usgs.parser import parse_usgs

log = structlog.get_logger(__name__)
SOURCE = "usgs"


def main() -> int:
    configure_logging()
    started_at = int(time.time())
    log.info("poll_starting", source=SOURCE, url=settings.poller_usgs_url)

    # ---- Fetch ----
    try:
        body = fetch(settings.poller_usgs_url, source=SOURCE)
    except RetriesExhausted as exc:
        write_events(SOURCE, [], started_at, "transient_fail", str(exc))
        log.error("poll_failed_network", source=SOURCE, error=str(exc))
        return 1
    except (ResponseTooLarge, CrossHostRedirect) as exc:
        write_events(SOURCE, [], started_at, "transient_fail", str(exc))
        log.error("poll_failed_hardening", source=SOURCE, error=str(exc))
        return 1

    # ---- Parse (structural failures only) ----
    try:
        events, parse_failures = parse_usgs(body)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        write_events(SOURCE, [], started_at, "parse_fail", f"{type(exc).__name__}: {exc}")
        log.error("poll_failed_parse", source=SOURCE, error=str(exc))
        return 1

    # ---- Partial-parse threshold (CONTEXT-locked behavior) ----
    outcome, outcome_summary = compute_parse_outcome(len(events), parse_failures)
    if outcome == "parse_fail":
        write_events(SOURCE, [], started_at, "parse_fail", outcome_summary)
        log.error(
            "poll_failed_parse_threshold",
            source=SOURCE,
            good=len(events),
            failures=parse_failures,
            summary=outcome_summary,
        )
        return 1

    # ---- Write good events + emit success audit row ----
    fetched, written = write_events(SOURCE, events, started_at, "success")
    log.info(
        "poll_complete",
        source=SOURCE,
        fetched=fetched,
        written=written,
        skipped_dedup=fetched - written,
        parse_failures=parse_failures,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
