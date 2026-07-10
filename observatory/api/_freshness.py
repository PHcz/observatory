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
    "weather": 900,  # 900s → HEALTHY_MULT(2)*900 == 1800s threshold per 03-CONTEXT.md
    "muon": 5,
    "usgs": 300,
    "emsc": 300,
    "bgs": 1800,
    "noaa": 900,
    "blitzortung": 30,
    "aurora": 900,
    # forecast polls hourly; HEALTHY_MULT(2)*3600 == 7200s healthy window.
    "forecast": 3600,
    # air_quality polls hourly; HEALTHY_MULT(2)*3600 == 7200s healthy window.
    "air_quality": 3600,
    # nmdb polls hourly; HEALTHY_MULT(2)*3600 == 7200s healthy window.
    "nmdb": 3600,
    # indoor air node publishes every ~60s; 120s interval → healthy < 4min, down >= 8min.
    "indoor": 120,
}

# Map source name -> (data table, optional source-column filter for earthquakes).
# NOTE: `forecast`, `air_quality` and `nmdb` are deliberately ABSENT here — their
# freshness must track {forecast,air_quality,nmdb}_meta.fetched_at (when we last
# polled), NOT MAX(ts) (forecast's horizon is 7 days ahead; air_quality is a
# single-row snapshot; nmdb_counts.ts is upstream data time, not poll time —
# Pitfall 2). health.py reads fetched_at directly for all three.
DATA_TABLE: Final[dict[str, tuple[str, str | None]]] = {
    "weather": ("weather", None),
    "muon": ("muon_events", None),
    "usgs": ("earthquakes", "usgs"),
    "emsc": ("earthquakes", "emsc"),
    "bgs": ("earthquakes", "bgs"),
    "noaa": ("space_weather", None),
    "blitzortung": ("lightning_strikes", None),
    "aurora": ("aurora_status", None),
    "indoor": ("indoor_air", None),
}

# Event-driven sources whose UPSTREAM data is genuinely sporadic: earthquakes
# happen at irregular intervals (USGS M-threshold quakes average ~90 min apart,
# BGS UK quakes are days apart), lightning only during storms (gaps of days),
# and aurora status changes rarely. For these, "time since last EVENT" is the
# WRONG freshness signal — a quiet quake-free hour or a storm-free week does not
# mean the feed is broken. Their traffic-light dot must reflect POLLER HEALTH
# (did we successfully poll on schedule?), anchored on the last successful poll
# — exactly as forecast/air_quality/nmdb anchor on *_meta.fetched_at. Continuous
# sources stay EVENT-anchored, where missing data genuinely is a fault: weather
# and muon emit a reading every interval, and noaa writes a space_weather row on
# every poll.
POLL_ANCHORED_SOURCES: Final[frozenset[str]] = frozenset(
    {"usgs", "emsc", "bgs", "blitzortung", "aurora"}
)

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


# UI-20: expected upstream cadence per source (seconds). DISTINCT from
# INTERVALS_SEC (the poller's CHECK cadence). When an upstream source hasn't
# published for > 2x its expected interval, cadence_warning fires.
#
# weather is dynamic — read from settings at call time so bench overrides apply.
EXPECTED_INTERVAL_SEC: Final[dict[str, int]] = {
    "muon": 60,  # 1 event/min minimum heartbeat
    "usgs": 300,  # 5min
    "emsc": 300,  # 5min
    "bgs": 1800,  # 30min
    "noaa": 900,  # 15min
    "blitzortung": 30,  # 30s
    "aurora": 900,  # 15min
    "forecast": 3600,  # 1h — UI-20 cadence_warning fires at 2x (2h overdue)
    "air_quality": 3600,  # 1h — UI-20 cadence_warning fires at 2x (2h overdue)
    "nmdb": 3600,  # 1h — UI-20 cadence_warning fires at 2x (2h overdue)
}


def cadence_warning(now: int, last_event_ts: int | None, source: str) -> bool:
    """Return True when the source is overdue by 2x its expected upstream cadence.

    For ``weather``, the expected interval is dynamic (read from
    ``settings.weather_expected_upload_sec`` at call time so test/bench overrides
    via env apply without re-import). For all other sources, the value is
    fixed in EXPECTED_INTERVAL_SEC above.

    Returns False when last_event_ts is None (no events yet) or when the
    source is unknown to EXPECTED_INTERVAL_SEC.

    Always False for POLL_ANCHORED_SOURCES: their upstream cadence is sporadic
    (sec during a storm, days between), so "overdue event" is meaningless — poll
    health is tracked by the freshness dot instead.
    """
    if source in POLL_ANCHORED_SOURCES:
        return False
    if last_event_ts is None:
        return False
    if source == "weather":
        from observatory.config import settings  # local import keeps tests cheap

        expected = int(settings.weather_expected_upload_sec)
    else:
        expected = EXPECTED_INTERVAL_SEC.get(source, 0)
    if expected <= 0:
        return False
    return (now - last_event_ts) > (2 * expected)
