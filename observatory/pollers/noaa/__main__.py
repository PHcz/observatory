"""NOAA SWPC combined poller — systemd oneshot entry point.

Composition: independent fetch+parse pairs (Kp / solar wind / IMF /
GOES protons / NOAA scales / GOES X-ray) -> ONE ``space_weather`` row per
run with NULL for whichever endpoint(s) failed -> always emit one
``poller_runs`` audit row.

Exit semantics (CONTEXT-locked partial-fetch tolerance):
  0 = success OR partial (at least one endpoint succeeded)
  1 = every endpoint failed (status='transient_fail', NO row written)

Each per-endpoint failure is tagged in ``error_summary`` with a label
(``kp:``, ``sw:``, ``imf:``, ``protons:``, ``scales:``, ``xray:``) and a
sub-tag (``network``, ``http`` (4xx, e.g. a retired URL), ``http_hardening``,
``parse``). One endpoint failing never stops the others.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from typing import TypeVar

import httpx
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
    parse_imf,
    parse_kp,
    parse_noaa_scales,
    parse_proton_flux,
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
    except httpx.HTTPStatusError as exc:
        # Non-retryable 4xx. Before 2026-10 this escaped and crashed the whole
        # poll when NOAA retired the old solar-wind URL, freezing Kp and flares.
        return None, f"{label}:http:{exc.response.status_code}"
    except httpx.HTTPError as exc:
        return None, f"{label}:http:{type(exc).__name__}"
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
    imf, e_imf = _safe_fetch(settings.poller_noaa_mag_url, parse_imf, "imf")
    protons, e_pr = _safe_fetch(settings.poller_noaa_protons_url, parse_proton_flux, "protons")
    scales, e_sc = _safe_fetch(settings.poller_noaa_scales_url, parse_noaa_scales, "scales")
    flare, e_xray = _safe_fetch(settings.poller_noaa_xray_url, parse_xray_flare, "xray")

    results = (e_kp, e_sw, e_imf, e_pr, e_sc, e_xray)
    errs = [e for e in results if e]

    if len(errs) == len(results):
        write_space_weather(None, started_at, "transient_fail", "; ".join(errs))
        log.error("noaa_all_failed", errors=errs)
        return 1

    snapshot = SpaceWeatherSnapshot(
        ts=started_at,
        kp_index=kp[1] if kp else None,
        solar_wind_kms=sw[1] if sw else None,
        flare_class=flare[0] if flare else None,
        flare_peak_ts=flare[1] if flare else None,
        solar_wind_density=sw[2] if sw else None,
        imf_bz_nt=imf[1] if imf else None,
        imf_bt_nt=imf[2] if imf else None,
        proton_flux_10mev=protons[1] if protons else None,
        noaa_scale_r=scales[0] if scales else None,
        noaa_scale_s=scales[1] if scales else None,
        noaa_scale_g=scales[2] if scales else None,
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
        imf_bz_nt=snapshot.imf_bz_nt,
        proton_flux_10mev=snapshot.proton_flux_10mev,
        flare_class=snapshot.flare_class,
        partial_errors=errs,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
