"""AuroraWatch UK status poller entry point.

Run as: ``python -m observatory.pollers.aurorawatch``

Wires hardened fetch + the AuroraWatch parser + the no-dedup aurora writer.
Exit codes:

- 0 on success (one aurora_status row written, poller_runs status=success)
- 1 on hard failure: network exhausted, response too large, off-host redirect,
  parse failure (malformed XML, missing elements, unknown status_id)

Per-source quirks vs Phase 4 pollers: single XML element, compact ``+0000``
tz carve-out lives in the parser, and there is no dedup — every poll writes
a fresh row because state transitions (green->amber etc.) are operationally
meaningful.
"""

from __future__ import annotations

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
from observatory.pollers._types import AuroraSnapshot
from observatory.pollers._write import write_aurora_status
from observatory.pollers.aurorawatch.parser import parse_aurora

SOURCE = "aurora"

log = structlog.get_logger(__name__)


def main() -> int:
    configure_logging()
    started_at = int(time.time())
    url = settings.poller_aurora_url
    log.info("poll_starting", source=SOURCE, url=url)

    # 1. Fetch (hardened)
    try:
        body = fetch(url, source=SOURCE)
    except RetriesExhausted as exc:
        write_aurora_status(None, started_at, "transient_fail", f"network:{exc}")
        log.error("aurora_fetch_failed", error=str(exc))
        return 1
    except (ResponseTooLarge, CrossHostRedirect) as exc:
        write_aurora_status(
            None,
            started_at,
            "transient_fail",
            f"http_hardening:{type(exc).__name__}: {exc}",
        )
        log.error("aurora_fetch_hardening", error=str(exc))
        return 1

    # 2. Parse — any ValueError = parse_fail (next timer fire retries; ROADMAP criterion 2)
    try:
        ts, status_str, detail = parse_aurora(body)
    except ValueError as exc:
        write_aurora_status(None, started_at, "parse_fail", f"parse:{exc}")
        log.warning("aurora_parse_fail", error=str(exc))
        return 1

    # 3. Success path — write the snapshot
    snapshot = AuroraSnapshot(ts=ts, status=status_str, detail=detail)
    write_aurora_status(snapshot, started_at, "success")
    log.info("aurora_complete", status=status_str, detail=detail, ts=ts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
