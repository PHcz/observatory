"""Forbush-decrease state machine (Phase 13, MU2-07) — pure function, no DB.

A Forbush decrease is a sudden drop in the galactic-cosmic-ray flux (and hence the
neutron-monitor count rate) following a coronal mass ejection, recovering over
days. Typical events are ~3-10% drops in the neutron count; small storms ~1-2%.
Those magnitudes set the thresholds below (documented project defaults, not a
standard).

Locked precedence (research §Forbush + CONTEXT):
  - NMDB %-baseline drop is the PRIMARY signal — it is statistically reliable
    (high, stable count rate). If NMDB data is absent we render Quiet with the
    locked awaiting-data detail line and never flag without that reliable signal.
  - NOAA Kp / solar-wind CORROBORATE the red escalation: a large NMDB drop only
    becomes "forbush" when a geomagnetic storm (Kp >= 5) or elevated solar wind
    (>= 500 km/s) confirms the space-weather context.
  - The small home detector's dip is SECONDARY confirmation only — its noisy
    Poisson stats can confirm but must NEVER raise an escalation alone (avoids
    false alarms).

State table (defaults below as config constants):
  | State   | StatusDot | Condition                                              |
  |---------|-----------|--------------------------------------------------------|
  | quiet   | green     | NMDB drop < 2%  (or NMDB absent)                       |
  | watch   | amber     | NMDB drop >= 2% (incl. >= 4% without corroboration)    |
  | forbush | red       | NMDB drop >= 4% AND (Kp >= 5 OR solar_wind >= 500 km/s)|

v1 baseline-window simplification: the drop is computed against a trailing 7-day
median rather than the canonical ~27-day solar-rotation climatology (see
``_baseline.BASELINE_WINDOW_DAYS``) because the home DB will not have 27 days of
data for a long time. Grow this once data accumulates.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

# Thresholds — documented project defaults (research §Forbush).
FORBUSH_WATCH_DROP_PCT = 2.0  # NMDB %-baseline drop -> Watch (nmdb_pct <= 98)
FORBUSH_ALERT_DROP_PCT = 4.0  # NMDB %-baseline drop -> Forbush candidate (nmdb_pct <= 96)
KP_CORROBORATION = 5.0  # NOAA Kp storm level corroborates the red escalation
SOLARWIND_CORROBORATION = 500.0  # km/s; elevated solar wind corroborates red
LOCAL_CONFIRM_DROP_PCT = 3.0  # local detector dip — SECONDARY confirm-only, never triggers
RECENT_WINDOW_SEC = 6 * 3600  # "recent" window for the drop (mean %-baseline over ~6h)

# Locked UI-SPEC empty-state copy (copy contract: keep character-for-character).
# The em-dash in the string is intentional UI-SPEC copy, not an ASCII slip.
_NMDB_ABSENT_DETAIL = "Awaiting neutron-monitor data — showing local detector only."


@dataclass(frozen=True)
class ForbushResult:
    """Outcome of the Forbush state machine.

    ``state`` maps to the StatusDot: quiet=green, watch=amber, forbush=red.
    ``detail`` is human copy explaining the state (locked line when NMDB absent).
    """

    state: str
    detail: str


def classify_forbush(
    *,
    nmdb_drop_pct: float | None,
    kp: float | None,
    solar_wind_kms: float | None,
    local_drop_pct: float | None,
) -> dict[str, Any]:
    """Classify the current Forbush state from the driving inputs.

    Pure function — no DB, no I/O. NMDB %-baseline drop is primary, NOAA
    Kp/solar-wind corroborate the red escalation, and the local detector dip is
    secondary confirmation only (never raises alone).

    Args:
        nmdb_drop_pct: NMDB %-baseline drop (100 - recent_pct); ``None`` means
            NMDB data is absent -> always Quiet with the locked detail line.
        kp: latest NOAA Kp index (corroboration), or ``None``.
        solar_wind_kms: latest solar-wind speed in km/s (corroboration), or ``None``.
        local_drop_pct: local detector %-baseline drop (secondary confirm-only),
            or ``None``.

    Returns:
        ``asdict(ForbushResult)`` -> ``{"state": str, "detail": str}`` with
        ``state`` in {"quiet", "watch", "forbush"}.
    """
    # NMDB primary: absent -> Quiet with the locked detail line, regardless of
    # any other input (we never flag without the reliable global reference).
    if nmdb_drop_pct is None:
        return asdict(ForbushResult(state="quiet", detail=_NMDB_ABSENT_DETAIL))

    # Below the Watch threshold -> Quiet. The local detector dip is secondary and
    # can never raise the state on its own, so it is not consulted here.
    if nmdb_drop_pct < FORBUSH_WATCH_DROP_PCT:
        return asdict(
            ForbushResult(
                state="quiet",
                detail="Neutron-monitor count steady — no Forbush decrease.",
            )
        )

    # Moderate drop (2% <= drop < 4%) -> Watch.
    if nmdb_drop_pct < FORBUSH_ALERT_DROP_PCT:
        return asdict(
            ForbushResult(
                state="watch",
                detail="Neutron-monitor count dipping — watching for a Forbush decrease.",
            )
        )

    # Large drop (>= 4%): escalate to red ONLY with NOAA corroboration.
    kp_storm = kp is not None and kp >= KP_CORROBORATION
    wind_high = solar_wind_kms is not None and solar_wind_kms >= SOLARWIND_CORROBORATION
    if kp_storm or wind_high:
        local_confirms = local_drop_pct is not None and local_drop_pct >= LOCAL_CONFIRM_DROP_PCT
        confirm = " Local detector confirms." if local_confirms else ""
        return asdict(
            ForbushResult(
                state="forbush",
                detail=f"Forbush decrease in progress — neutron count down with storm-level "
                f"space weather.{confirm}",
            )
        )

    # Large drop but no space-weather corroboration -> stays Watch (not red).
    return asdict(
        ForbushResult(
            state="watch",
            detail="Neutron-monitor count low but no corroborating space weather yet.",
        )
    )
