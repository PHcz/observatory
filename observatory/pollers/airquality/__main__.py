"""Open-Meteo air-quality poller — systemd oneshot entry point (Phase 11, OAQ-01).

Composition: one hardened fetch (shared SEC-05 ``_http.fetch``) -> current-object
``parse_air_quality`` -> replace-on-fetch ``write_air_quality`` -> always emit one
``poller_runs`` audit row.

Exit semantics (graceful degradation):
  0 = success (snapshot cached, one audit row)
  1 = fetch failure (status='transient_fail') or parse failure (status='parse_fail');
      no air_quality row written, audit row still emitted.

No ``Restart=`` in the systemd unit — the hourly timer IS the retry (STATE 04-05).
The home coordinates are injected at runtime from settings.home_lat/home_lon and are
never present in any committed string (CLAUDE.md security gate).
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
from observatory.pollers._write import write_air_quality
from observatory.pollers.airquality.parser import parse_air_quality

log = structlog.get_logger(__name__)
SOURCE = "air_quality"


def main() -> int:
    configure_logging()
    started_at = int(time.time())
    log.info("poll_starting", source=SOURCE)

    url = settings.poller_air_quality_url.format(lat=settings.home_lat, lon=settings.home_lon)
    try:
        body = fetch(url, source=SOURCE)
    except (RetriesExhausted, ResponseTooLarge, CrossHostRedirect) as exc:
        write_air_quality(
            None, None, started_at, "transient_fail", f"fetch:{type(exc).__name__}:{exc}"
        )
        log.error("air_quality_fetch_failed", error=str(exc))
        return 1

    try:
        snapshot, meta = parse_air_quality(body)
    except ValueError as exc:
        write_air_quality(None, None, started_at, "parse_fail", f"parse:{exc}")
        log.error("air_quality_parse_failed", error=str(exc))
        return 1

    write_air_quality(snapshot, meta, started_at, "success", None)
    log.info("air_quality_complete", source=SOURCE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
