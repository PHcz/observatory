"""Pure-function freshness derivation for /api/health (Plan 05-05).

Testable without DB or FastAPI. Constants and helpers consumed by
``observatory.api.routers.health`` to compute per-source freshness from event
age (vs interval) and to apply the poller_runs cross-check override.

Thresholds locked in 05-CONTEXT.md staleness threshold table:
  - healthy: age < HEALTHY_MULT * interval (2x)
  - stale:   age < STALE_MULT   * interval (4x)
  - down:    age >= STALE_MULT  * interval

The cross-check rule (also per CONTEXT): if the last poller_runs row is
``transient_fail`` within the down window, OR the last poll itself is older
than the down threshold (poller silent), the source is forced to ``"down"``
regardless of last event timestamp. ``partial`` (NOAA 1-of-3 / 2-of-3) is
treated as healthy from the data-freshness perspective per 05-02 SUMMARY.
"""

from __future__ import annotations

from typing import Final, Literal

Freshness = Literal["healthy", "stale", "down"]

HEALTHY_MULT: Final[int] = 2
STALE_MULT: Final[int] = 4

# Per-source intervals (seconds). Locked verbatim from 05-CONTEXT.md table.
INTERVALS_SEC: Final[dict[str, int]] = {
    "weather": 300,
    "muon": 5,
    "usgs": 300,
    "emsc": 300,
    "bgs": 1800,
    "noaa": 900,
    "blitzortung": 30,
    "aurora": 900,
}

# Map source name -> (data table, optional source-column filter for earthquakes).
DATA_TABLE: Final[dict[str, tuple[str, str | None]]] = {
    "weather": ("weather", None),
    "muon": ("muon_events", None),
    "usgs": ("earthquakes", "usgs"),
    "emsc": ("earthquakes", "emsc"),
    "bgs": ("earthquakes", "bgs"),
    "noaa": ("space_weather", None),
    "blitzortung": ("lightning_strikes", None),
    "aurora": ("aurora_status", None),
}

_RANK: Final[dict[str, int]] = {"healthy": 0, "stale": 1, "down": 2}


def freshness(age_sec: float, interval_sec: int) -> Freshness:
    """Compute freshness bucket from event age vs poll interval."""
    if age_sec < HEALTHY_MULT * interval_sec:
        return "healthy"
    if age_sec < STALE_MULT * interval_sec:
        return "stale"
    return "down"


def worst(a: Freshness, b: Freshness) -> Freshness:
    """Return the worst (most-degraded) of two freshness values."""
    return a if _RANK[a] >= _RANK[b] else b


def cross_check_poller(
    event_freshness: Freshness,
    last_poll_status: str | None,
    last_poll_ts: int | None,
    now: int,
    interval_sec: int,
) -> Freshness:
    """Apply the CONTEXT poller_runs override rule.

    - Recent ``transient_fail`` (within down window) -> ``"down"``.
    - Last poll older than down threshold (poller silent) -> ``"down"``.
    - Otherwise return the event-derived freshness unchanged.

    ``success``, ``partial``, ``parse_fail``, and ``None`` (no history) all
    preserve event freshness — partial because NOAA still wrote a row,
    parse_fail because the poller is responsive (data-quality issue only),
    and no-history because we genuinely don't know yet.
    """
    down_threshold = STALE_MULT * interval_sec
    if last_poll_ts is not None:
        age = now - last_poll_ts
        # Recent transient_fail forces down regardless of event freshness.
        if last_poll_status == "transient_fail" and age < down_threshold:
            return "down"
        # Silent-poller override applies only when the last poll was otherwise
        # healthy (success/partial): we had proof the poller was alive, then
        # it went quiet. transient_fail/parse_fail already explain any silence
        # (and a recent transient_fail is handled above).
        if last_poll_status in ("success", "partial") and age >= down_threshold:
            return "down"
    return event_freshness
