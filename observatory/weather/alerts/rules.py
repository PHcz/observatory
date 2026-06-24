"""Phase 16 ENH-04: Alert rule protocol + implementations.

Ships FrostRule + PressureFallRule ONLY.
Stale-source and low-battery rules are DEFERRED — do NOT add.

Extensibility: new rules implement the AlertRule Protocol and are appended
to ACTIVE_RULES. No refactoring required.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Protocol

import structlog

import observatory.config as _config_mod

log = structlog.get_logger(__name__)


@dataclass
class AlertResult:
    """Result of evaluating a single alert rule."""

    rule: str  # "frost_risk" | "rapid_pressure_fall"
    severity: str  # "warn" | "alert"
    detail: str  # human-readable description for the alert row
    triggered: bool


class AlertRule(Protocol):
    """Extensible protocol for weather alert rules.

    New rules implement evaluate(conn) -> AlertResult and are appended to
    ACTIVE_RULES without any other changes.
    """

    rule: str

    def evaluate(self, conn: sqlite3.Connection) -> AlertResult: ...


class FrostRule:
    """Frost/freeze risk rule.

    Triggered when:
      - Latest temp_c < settings.alert_frost_temp_c (default 2.0°C)
      - AND (temp_c - dewpoint_c) < settings.alert_frost_dewpoint_spread_c (default 2.0°C)

    Dewpoint uses the simplified Magnus formula: T_d = T - (100 - RH) / 5
    which is already implemented in observatory.weather.derived.dewpoint_c.
    """

    rule = "frost_risk"

    def evaluate(self, conn: sqlite3.Connection) -> AlertResult:
        row = conn.execute(
            "SELECT temp_c, humidity_pct FROM weather ORDER BY ts DESC LIMIT 1"
        ).fetchone()

        if row is None or row[0] is None or row[1] is None:
            return AlertResult(
                rule=self.rule,
                severity="warn",
                detail="No weather data available",
                triggered=False,
            )

        temp_c: float = float(row[0])
        humidity_pct: float = float(row[1])

        # Simplified Magnus dewpoint: T_d = T - (100 - RH) / 5
        try:
            from observatory.weather.derived import dewpoint_c

            dp = dewpoint_c(temp_c, humidity_pct)
        except ImportError:
            # Fallback in case derived.py is not yet present (wave ordering)
            dp = temp_c - (100.0 - humidity_pct) / 5.0

        spread = temp_c - dp
        _settings = _config_mod.settings
        triggered = (
            temp_c < _settings.alert_frost_temp_c
            and spread < _settings.alert_frost_dewpoint_spread_c
        )

        detail = f"Temp {temp_c:.1f}°C, dewpoint {dp:.1f}°C (spread {spread:.1f}°C)"
        return AlertResult(
            rule=self.rule,
            severity="warn",
            detail=detail,
            triggered=triggered,
        )


class PressureFallRule:
    """Rapid pressure fall rule (storm risk).

    Triggered when the 3-hour pressure delta is more negative than
    -settings.alert_pressure_fall_hpa_per_3h (default -1.6 hPa).

    Looks for the closest weather row to (now - 3h); requires at least two
    rows separated by roughly 3 hours.
    """

    rule = "rapid_pressure_fall"

    def evaluate(self, conn: sqlite3.Connection) -> AlertResult:
        import time

        now = int(time.time())
        three_h_ago = now - 3 * 3600

        # Latest reading
        now_row = conn.execute(
            "SELECT pressure_hpa FROM weather ORDER BY ts DESC LIMIT 1"
        ).fetchone()

        # Closest row to 3h ago (find row with minimum |ts - three_h_ago|)
        past_row = conn.execute(
            "SELECT pressure_hpa FROM weather ORDER BY ABS(ts - ?) LIMIT 1",
            (three_h_ago,),
        ).fetchone()

        if now_row is None or past_row is None:
            return AlertResult(
                rule=self.rule,
                severity="warn",
                detail="Insufficient pressure history",
                triggered=False,
            )

        if now_row[0] is None or past_row[0] is None:
            return AlertResult(
                rule=self.rule,
                severity="warn",
                detail="Pressure data unavailable",
                triggered=False,
            )

        pressure_now: float = float(now_row[0])
        pressure_then: float = float(past_row[0])
        delta: float = pressure_now - pressure_then

        triggered = delta < -_config_mod.settings.alert_pressure_fall_hpa_per_3h

        detail = f"{delta:+.1f} hPa in 3 h" + (" · storm risk" if triggered else "")
        return AlertResult(
            rule=self.rule,
            severity="warn",
            detail=detail,
            triggered=triggered,
        )


def _format_age(seconds: int) -> str:
    """Compact human duration: '18 h 20 m', '45 m', '90 s'."""
    if seconds < 60:
        return f"{seconds} s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} m"
    hours, mins = divmod(minutes, 60)
    return f"{hours} h {mins} m" if mins else f"{hours} h"


class StaleEnviroRule:
    """Outdoor Enviro weather node offline rule.

    Triggered when the newest weather reading is older than
    settings.alert_enviro_stale_sec (default 3600 s = 1 h). The Enviro publishes
    every ~5 min, so an hour of silence means a dead battery or wifi loss — the
    exact failure that swallowed ~18 h of data on the 2026-06-23 battery outage.

    Empty table (fresh install, board never reported) is NOT triggered: there is
    no baseline to be "stale" against, and alarming on first boot is noise.

    Time-based, not data-arrival-based: evaluate_rules() runs every ~60 s in the
    db_watcher loop regardless of new rows, so this fires even while data is
    absent. Recovery (data resumes → age under threshold) resolves it.
    """

    rule = "enviro_stale"

    def evaluate(self, conn: sqlite3.Connection) -> AlertResult:
        import time

        threshold = _config_mod.settings.alert_enviro_stale_sec
        row = conn.execute("SELECT ts FROM weather ORDER BY ts DESC LIMIT 1").fetchone()

        if row is None or row[0] is None:
            # No reading ever — nothing to be stale against.
            return AlertResult(
                rule=self.rule, severity="alert", detail="No weather data yet", triggered=False
            )

        last_ts = int(row[0])
        age = int(time.time()) - last_ts
        triggered = age > threshold

        last_local = time.strftime("%Y-%m-%d %H:%M", time.localtime(last_ts))
        detail = f"No reading from Enviro for {_format_age(age)} (last: {last_local})"
        return AlertResult(rule=self.rule, severity="alert", detail=detail, triggered=triggered)


# ACTIVE_RULES — append new rules here.
# StaleEnviroRule added 2026-06-24 by explicit request (battery-outage alerting),
# overriding the original Phase-16 deferral of stale-source rules.
ACTIVE_RULES: list[AlertRule] = [FrostRule(), PressureFallRule(), StaleEnviroRule()]
