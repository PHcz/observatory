"""Forbush-decrease state machine (Phase 13, MU2-07) — pure function, no DB.

Wave-0 RED skeleton: ``classify_forbush`` raises NotImplementedError. Wave 4
(plan 13-05) implements the locked precedence (NMDB %-baseline drop PRIMARY; NOAA
Kp / solar-wind CORROBORATE the red escalation; local detector dip SECONDARY,
never raises alone; NMDB-absent -> Quiet with the locked detail line).

Thresholds (config constants, research §Forbush):
  FORBUSH_WATCH_DROP_PCT  = 2.0
  FORBUSH_ALERT_DROP_PCT  = 4.0
  KP_CORROBORATION        = 5.0
  SOLARWIND_CORROBORATION = 500.0
  LOCAL_CONFIRM_DROP_PCT  = 3.0
  RECENT_WINDOW_SEC       = 6 * 3600
"""

from __future__ import annotations

from typing import Any

FORBUSH_WATCH_DROP_PCT = 2.0
FORBUSH_ALERT_DROP_PCT = 4.0
KP_CORROBORATION = 5.0
SOLARWIND_CORROBORATION = 500.0
LOCAL_CONFIRM_DROP_PCT = 3.0
RECENT_WINDOW_SEC = 6 * 3600


def classify_forbush(
    *,
    nmdb_drop_pct: float | None,
    kp: float | None,
    solar_wind_kms: float | None,
    local_drop_pct: float | None,
) -> dict[str, Any]:
    """Classify the current Forbush state from the inputs.

    Implemented in Wave 4 (plan 13-05).
    """
    raise NotImplementedError("classify_forbush is implemented in Wave 4 (plan 13-05)")
