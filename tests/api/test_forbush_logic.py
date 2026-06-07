"""RED tests for the Forbush state machine (Phase 13, MU2-07).

Imports classify_forbush from observatory.api._forbush, which Wave 4 (plan 13-05)
creates -> import fails RED until then.

Locked precedence (research §Forbush): NMDB %-baseline drop is PRIMARY; NOAA Kp /
solar-wind CORROBORATE the red escalation; the local detector dip is SECONDARY
confirmation only and can never raise alone. When NMDB is unavailable, render
Quiet with the locked detail line.

Thresholds (config constants, research §Forbush):
  FORBUSH_WATCH_DROP_PCT  = 2.0   # nmdb_pct <= 98
  FORBUSH_ALERT_DROP_PCT  = 4.0   # nmdb_pct <= 96
  KP_CORROBORATION        = 5.0
  SOLARWIND_CORROBORATION = 500.0
  LOCAL_CONFIRM_DROP_PCT  = 3.0
"""

from __future__ import annotations

from observatory.api._forbush import classify_forbush


def test_quiet_when_no_nmdb_drop() -> None:
    out = classify_forbush(nmdb_drop_pct=0.5, kp=2.0, solar_wind_kms=380.0, local_drop_pct=0.0)
    assert out["state"] == "quiet"


def test_watch_on_moderate_nmdb_drop_without_corroboration() -> None:
    # drop >= 2% and < 4% -> Watch.
    out = classify_forbush(nmdb_drop_pct=3.0, kp=2.0, solar_wind_kms=380.0, local_drop_pct=0.0)
    assert out["state"] == "watch"


def test_forbush_on_large_drop_with_kp_corroboration() -> None:
    # drop >= 4.0 AND Kp >= 5 -> Forbush in progress.
    out = classify_forbush(nmdb_drop_pct=4.5, kp=6.0, solar_wind_kms=380.0, local_drop_pct=0.0)
    assert out["state"] == "forbush"


def test_forbush_on_large_drop_with_solar_wind_corroboration() -> None:
    # drop >= 4.0 AND solar_wind >= 500 -> Forbush in progress.
    out = classify_forbush(nmdb_drop_pct=5.0, kp=2.0, solar_wind_kms=550.0, local_drop_pct=0.0)
    assert out["state"] == "forbush"


def test_large_drop_without_corroboration_stays_watch() -> None:
    # drop >= 4.0 but neither Kp nor solar wind elevated -> NOT red; stays Watch.
    out = classify_forbush(nmdb_drop_pct=5.0, kp=2.0, solar_wind_kms=380.0, local_drop_pct=0.0)
    assert out["state"] == "watch"


def test_local_dip_never_triggers_alone() -> None:
    # No NMDB drop but a large local detector dip -> still Quiet (secondary only).
    out = classify_forbush(nmdb_drop_pct=0.0, kp=2.0, solar_wind_kms=380.0, local_drop_pct=10.0)
    assert out["state"] == "quiet"


def test_nmdb_absent_renders_quiet_with_locked_detail() -> None:
    out = classify_forbush(nmdb_drop_pct=None, kp=2.0, solar_wind_kms=380.0, local_drop_pct=5.0)
    assert out["state"] == "quiet"
    assert "Awaiting neutron-monitor data" in out["detail"]
