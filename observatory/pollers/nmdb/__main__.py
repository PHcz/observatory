"""NMDB / NEST neutron-monitor poller — systemd oneshot entry point (Phase 13, MU2-06).

Composition: one hardened fetch (shared SEC-05 ``_http.fetch``) -> strict+tolerant
``parse_nmdb`` -> partial-parse threshold (``compute_parse_outcome`` over good vs
gap/null rows) -> append-window ``write_nmdb`` -> always emit one ``poller_runs``
audit row.

Exit semantics (graceful degradation):
  0 = success (counts appended, one audit row)
  1 = fetch failure (status='transient_fail') or parse failure (status='parse_fail',
      structural OR over-threshold gap ratio); no rows written, audit row emitted.

The Oulu station is the canonical global Forbush reference; the station is
configurable via ``settings.poller_nmdb_station`` and substituted into the NEST
URL template at runtime. ``yunits=0`` (counts/s) is pinned in the config URL
(Pitfall 3). No ``Restart=`` in the systemd unit — the hourly timer IS the retry
(STATE 04-05). NMDB asks scripted users to cite the database; see README.

``fetch`` / ``configure_logging`` / ``settings`` are imported by name so the test
harness can monkeypatch them (the poller-conftest rebind loops register this
module) exactly as for the airquality/forecast pollers.
"""

from __future__ import annotations

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
from observatory.pollers._write import compute_parse_outcome, write_nmdb
from observatory.pollers.nmdb.parser import parse_nmdb

log = structlog.get_logger(__name__)
SOURCE = "nmdb"

__all__ = [
    "CrossHostRedirect",
    "ResponseTooLarge",
    "RetriesExhausted",
    "compute_parse_outcome",
    "configure_logging",
    "fetch",
    "main",
    "parse_nmdb",
    "settings",
    "write_nmdb",
]


def main() -> int:
    configure_logging()
    started_at = int(time.time())
    log.info("poll_starting", source=SOURCE)

    url = settings.poller_nmdb_url.format(station=settings.poller_nmdb_station)
    try:
        body = fetch(url, source=SOURCE)
    except (RetriesExhausted, ResponseTooLarge, CrossHostRedirect) as exc:
        write_nmdb(None, None, started_at, "transient_fail", f"fetch:{type(exc).__name__}:{exc}")
        log.error("nmdb_fetch_failed", error=str(exc))
        return 1

    try:
        counts, meta = parse_nmdb(body, settings.poller_nmdb_station)
    except ValueError as exc:
        write_nmdb(None, None, started_at, "parse_fail", f"parse:{exc}")
        log.error("nmdb_parse_failed", error=str(exc))
        return 1

    failures = int(meta.get("failures", 0))
    good = len(counts) - failures
    outcome, outcome_summary = compute_parse_outcome(good, failures)
    if outcome == "parse_fail":
        write_nmdb(None, None, started_at, "parse_fail", outcome_summary)
        log.error("nmdb_parse_threshold", good=good, failures=failures, summary=outcome_summary)
        return 1

    write_nmdb(counts, meta, started_at, "success", None)
    log.info("nmdb_complete", source=SOURCE, rows=len(counts), gaps=failures)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
