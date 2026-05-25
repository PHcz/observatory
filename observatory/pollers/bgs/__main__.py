"""BGS UK earthquakes poller entry point.

Run as: ``python -m observatory.pollers.bgs``

Wires the hardened fetch + the BGS-specific parser + the dedup-aware writer.
Exit codes:

- 0 on success (events written, OR empty fetch — quiet seismic period)
- 0 on partial parse under threshold (writes the good rows, logs WARNINGs)
- 1 on hard failure: network exhausted, response too large, off-host
  redirect, structural parse error, OR per-item parse_failures ratio
  EXCEEDING ``POLLER_PARSE_FAILURE_THRESHOLD`` (writes 0 rows in that case).

Per-source quirks vs USGS/EMSC: BGS feed is RSS (parsed via defusedxml —
billion-laughs / external-entity defenses), no <guid> (external_id derived
from <link>), naive pubDate (BGS parser assumes UTC itself rather than
routing through the strict parse_ts).
"""

from __future__ import annotations

import sys
import time

import defusedxml.ElementTree as ET
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
from observatory.pollers.bgs.parser import parse_bgs

SOURCE = "bgs"

log = structlog.get_logger(__name__)


def main() -> int:
    configure_logging()
    started_at = int(time.time())
    url = settings.poller_bgs_url
    log.info("poll_starting", source=SOURCE, url=url)

    # 1. Fetch (hardened)
    try:
        body = fetch(url, source=SOURCE)
    except RetriesExhausted as exc:
        write_events(SOURCE, [], started_at, "transient_fail", f"{type(exc).__name__}: {exc}")
        log.error("poll_failed_network", source=SOURCE, error=str(exc))
        return 1
    except (ResponseTooLarge, CrossHostRedirect) as exc:
        write_events(SOURCE, [], started_at, "transient_fail", f"{type(exc).__name__}: {exc}")
        log.error("poll_failed_hardening", source=SOURCE, error=str(exc))
        return 1

    # 2. Parse (structural failure -> exit 1; per-item failure -> counter)
    try:
        events, parse_failures = parse_bgs(body)
    except (ET.ParseError, KeyError, TypeError, ValueError, AttributeError) as exc:
        write_events(SOURCE, [], started_at, "parse_fail", f"{type(exc).__name__}: {exc}")
        log.error("poll_failed_parse", source=SOURCE, error=str(exc))
        return 1

    # 3. Decide outcome from per-item failure ratio
    status, error_summary = compute_parse_outcome(len(events), parse_failures)
    if status != "success":
        # Over threshold: write 0 events but record the audit row
        write_events(SOURCE, [], started_at, status, error_summary)
        log.error(
            "poll_failed_parse_threshold",
            source=SOURCE,
            good=len(events),
            failures=parse_failures,
            summary=error_summary,
        )
        return 1

    # 4. Success path: write the good events
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
