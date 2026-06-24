"""Daily Enviro health heartbeat -> Telegram.

Sends ONE status message a day, healthy or not, so the operator knows both that
the outdoor weather node is reporting AND that the monitoring pipeline itself is
alive. The stale-Enviro alert is silence-is-good, so without a heartbeat a quiet
day is indistinguishable from a dead monitor. This always sends:

    ✅ online  — last reading recent, with the latest values + 24 h count
    ⚠️ STALE   — last reading older than ALERT_ENVIRO_STALE_SEC

Runs on the Pi via obs-enviro-heartbeat.timer. Outbound-only (Telegram), same
sanctioned-egress justification as the pollers and threshold alerts.

Exit codes:
    0  message sent (or Telegram disabled — a no-op, not a failure)
    1  the DB read failed (a best-effort warning is still attempted)

Config: reuses ALERT_TELEGRAM_* for delivery and ALERT_ENVIRO_STALE_SEC for the
healthy/stale boundary. No new settings.
"""

from __future__ import annotations

import asyncio
import sqlite3
import sys
import time
from typing import Any

import structlog

from observatory.config import settings
from observatory.db.connection import get_conn
from observatory.weather.alerts.notifier import notify_telegram
from observatory.weather.alerts.rules import _format_age

log = structlog.get_logger(__name__)


def gather_stats(conn: sqlite3.Connection, now: int) -> dict[str, Any]:
    """Latest weather row + count of readings in the last 24 h."""
    row = conn.execute(
        "SELECT ts, temp_c, humidity_pct, pressure_hpa FROM weather ORDER BY ts DESC LIMIT 1"
    ).fetchone()
    count_24h = int(
        conn.execute("SELECT COUNT(*) FROM weather WHERE ts >= ?", (now - 86400,)).fetchone()[0]
    )
    if row is None:
        return {"last_ts": None, "count_24h": count_24h}
    return {
        "last_ts": int(row["ts"]),
        "temp_c": row["temp_c"],
        "humidity_pct": row["humidity_pct"],
        "pressure_hpa": row["pressure_hpa"],
        "count_24h": count_24h,
    }


def build_message(stats: dict[str, Any], now: int, stale_threshold: int) -> str:
    """Human-readable heartbeat body (worst case still informative)."""
    count = stats["count_24h"]
    last_ts = stats.get("last_ts")
    if last_ts is None:
        return "⚠️ Enviro health: no weather data on record yet."

    age = now - last_ts
    last_local = time.strftime("%H:%M", time.localtime(last_ts))
    stale = age > stale_threshold
    head = "⚠️ Enviro health: STALE" if stale else "✅ Enviro health: online"

    lines = [
        head,
        f"Last reading: {_format_age(age)} ago ({last_local})",
        f"Readings in 24 h: {count}",
    ]
    temp = stats.get("temp_c")
    hum = stats.get("humidity_pct")
    pres = stats.get("pressure_hpa")
    if temp is not None and pres is not None:
        rh = f", {hum:.0f}% RH" if hum is not None else ""
        lines.append(f"Now: {temp:.1f}°C{rh}, {pres:.0f} hPa")
    return "\n".join(lines)


async def _amain() -> int:
    now = int(time.time())
    try:
        conn = get_conn()
        try:
            stats = gather_stats(conn, now)
        finally:
            conn.close()
    except Exception as exc:
        log.error("enviro_heartbeat.db_failed", error=str(exc))
        await notify_telegram(
            title="Observatory daily check",
            message=f"⚠️ Heartbeat ran but the DB read failed: {exc}",
        )
        return 1

    message = build_message(stats, now, settings.alert_enviro_stale_sec)
    await notify_telegram(title="Observatory daily check", message=message)
    log.info("enviro_heartbeat.sent", count_24h=stats["count_24h"], stale=stats.get("last_ts"))
    return 0


def main() -> int:
    return asyncio.run(_amain())


if __name__ == "__main__":
    sys.exit(main())
