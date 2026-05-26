"""NOAA SWPC combined poller — systemd oneshot entry point.

Composition: 3 independent fetch+parse pairs (Kp / solar wind / GOES
X-ray) -> ONE ``space_weather`` row per run with NULL for whichever
endpoint(s) failed -> always emit one ``poller_runs`` audit row.

Exit semantics (CONTEXT-locked partial-fetch tolerance):
  0 = success OR partial (1-of-3 / 2-of-3 endpoints succeeded)
  1 = all 3 endpoints failed (status='transient_fail', NO row written)

Each per-endpoint failure is tagged in ``error_summary`` with a label
(``kp:``, ``sw:``, ``xray:``) and a sub-tag (``network``,
``http_hardening``, ``parse``).
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from typing import TypeVar

import structlog

from observatory.config import settings
from observatory.logging import configure_logging
from observatory.pollers._http import (
    CrossHostRedirect,
    ResponseTooLarge,
    RetriesExhausted,
    fetch,
)
from observatory.pollers._types import SpaceWeatherSnapshot
from observatory.pollers._write import write_space_weather
from observatory.pollers.noaa.parser import (
    parse_kp,
    parse_solar_wind,
    parse_xray_flare,
)

log = structlog.get_logger(__name__)
SOURCE = "noaa"

T = TypeVar("T")


def _safe_fetch(
    url: str,
    parse_fn: Callable[[bytes], T],
    label: str,
) -> tuple[T | None, str | None]:
    """Fetch+parse one endpoint; return ``(result, None)`` or ``(None, error_tag)``."""
    try:
        body = fetch(url, source=SOURCE)
    except RetriesExhausted as exc:
        return None, f"{label}:network:{exc}"
    except (ResponseTooLarge, CrossHostRedirect) as exc:
        return None, f"{label}:http_hardening:{type(exc).__name__}"
    try:
        return parse_fn(body), None
    except ValueError as exc:
        return None, f"{label}:parse:{exc}"


def main() -> int:
    configure_logging()
    started_at = int(time.time())
    log.info("poll_starting", source=SOURCE)

    kp, e_kp = _safe_fetch(settings.poller_noaa_kp_url, parse_kp, "kp")
    sw, e_sw = _safe_fetch(settings.poller_noaa_solar_wind_url, parse_solar_wind, "sw")
    flare, e_xray = _safe_fetch(settings.poller_noaa_xray_url, parse_xray_flare, "xray")

    errs = [e for e in (e_kp, e_sw, e_xray) if e]

    if len(errs) == 3:
        write_space_weather(None, started_at, "transient_fail", "; ".join(errs))
        log.error("noaa_all_failed", errors=errs)
        return 1

    snapshot = SpaceWeatherSnapshot(
        ts=started_at,
        kp_index=kp[1] if kp else None,
        solar_wind_kms=sw[1] if sw else None,
        flare_class=flare[0] if flare else None,
        flare_peak_ts=flare[1] if flare else None,
    )
    status = "partial" if errs else "success"
    error_summary = "; ".join(errs) if errs else None
    write_space_weather(snapshot, started_at, status, error_summary)
    log.info(
        "noaa_complete",
        source=SOURCE,
        status=status,
        kp=snapshot.kp_index,
        solar_wind_kms=snapshot.solar_wind_kms,
        flare_class=snapshot.flare_class,
        partial_errors=errs,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
