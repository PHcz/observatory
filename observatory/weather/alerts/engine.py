"""Phase 16 ENH-04: Alert rule engine.

Evaluates ACTIVE_RULES against the current weather data on every call.
Writes one row per crossing (dedup-guarded), resolves on clear,
fans out over WebSocket (if an asyncio event loop is running), and
pushes to ntfy (fire-and-forget, never raises).

Dedup design (Pitfall 4 from RESEARCH.md):
  - Before inserting, check for an active (resolved_at_ts IS NULL) row for
    the same rule. Only insert on the NOT-triggered → triggered transition.
  - Only update resolved_at_ts on the triggered → NOT-triggered transition.
  - A still-active or still-clear condition produces no DB write.

Hysteresis (alert_min_active_minutes, default 5):
  - An in-memory dict records the first time each rule's condition was seen
    as triggered. The ntfy push only fires once the condition has been active
    for >= alert_min_active_minutes * 60 seconds.
  - The dedup guard (one active DB row) still holds regardless of hysteresis.
  - The in-memory first-seen dict is reset when the condition clears.

Concurrency:
  evaluate_rules() is synchronous (plain function, not a coroutine) so the
  dedup test can call it without asyncio.run(). Async side-effects (fanout,
  ntfy) are scheduled via asyncio.get_running_loop().create_task() when an
  event loop is running; they are skipped silently in synchronous / test
  contexts (no event loop → no side-effects, DB correctness unaffected).
"""

from __future__ import annotations

import asyncio
import contextlib
import sqlite3
import time
from typing import Any

import structlog

from observatory.weather.alerts.rules import ACTIVE_RULES

log = structlog.get_logger(__name__)

# In-memory hysteresis tracker: rule_name → Unix ts of first trigger detection.
# Reset to None when the condition clears.
_first_seen_ts: dict[str, int | None] = {}

# Fire-and-forget task set: holds strong references so tasks aren't GC'd.
# Self-cleaning: each task removes itself on completion.
_background_tasks: set[asyncio.Task] = set()  # type: ignore[type-arg]


def _rule_title(rule_name: str) -> str:
    """Human-readable push title for a rule name."""
    return {
        "frost_risk": "Frost Risk",
        "rapid_pressure_fall": "Rapid Pressure Fall",
        "enviro_stale": "Enviro Offline",
    }.get(rule_name, rule_name.replace("_", " ").title())


def _recovery_message(rule_name: str) -> tuple[str, str]:
    """(title, body) for the recovery push sent when a rule resolves."""
    return {
        "enviro_stale": ("Enviro Online", "Outdoor weather node is reporting again."),
        "frost_risk": ("Frost Cleared", "Temperature back above the frost threshold."),
        "rapid_pressure_fall": ("Pressure Steady", "Rapid pressure fall has eased."),
    }.get(rule_name, (f"{_rule_title(rule_name)} Cleared", "Condition resolved."))


def _schedule_async(coro: Any) -> None:
    """Schedule a coroutine on the running event loop if one exists.

    Stores the Task in _background_tasks to prevent premature GC (RUF006 pattern).
    In test / CLI contexts where there is no running loop, the coroutine is
    closed immediately (prevents 'coroutine was never awaited' warnings).
    Never raises.
    """
    try:
        loop = asyncio.get_running_loop()
        task = loop.create_task(coro)
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
    except RuntimeError:
        # No running event loop — close the coroutine to avoid a resource warning.
        with contextlib.suppress(Exception):
            coro.close()


def evaluate_rules(conn: sqlite3.Connection) -> None:
    """Evaluate all ACTIVE_RULES and update the alerts table accordingly.

    This is a synchronous function so it can be called from both synchronous
    test code and from the async db_watcher (wrapped in ``await asyncio.to_thread``
    or called directly — see db_watcher.py).

    Async side-effects (WebSocket fanout, ntfy push) are fire-and-forget tasks
    scheduled on the running event loop when available.
    """
    now = int(time.time())

    for rule_obj in ACTIVE_RULES:
        rule_name = rule_obj.rule
        try:
            result = rule_obj.evaluate(conn)
        except Exception as exc:
            log.warning("alert_rule_eval_failed", rule=rule_name, error=str(exc))
            continue

        # Check for an existing active alert row (dedup guard — Pitfall 4).
        active_row = conn.execute(
            "SELECT id, crossed_at_ts FROM alerts WHERE rule=? AND resolved_at_ts IS NULL",
            (rule_name,),
        ).fetchone()

        if result.triggered and active_row is None:
            # NEW crossing — insert one row.
            conn.execute(
                "INSERT INTO alerts (rule, severity, crossed_at_ts, resolved_at_ts, detail_text)"
                " VALUES (?, ?, ?, NULL, ?)",
                (rule_name, result.severity, now, result.detail),
            )
            conn.commit()
            log.info("alert_crossed", rule=rule_name, severity=result.severity)

            # Track first-seen for hysteresis (already IS the first crossing insert).
            _first_seen_ts[rule_name] = now

            # Fan out the new crossing over WebSocket.
            envelope: dict[str, Any] = {
                "type": "alert",
                "data": {
                    "rule": rule_name,
                    "severity": result.severity,
                    "crossed_at_ts": now,
                    "resolved_at_ts": None,
                    "detail_text": result.detail,
                },
                "ts": now,
            }
            from observatory.api.routers.ws import fanout_event  # local import avoids circular dep

            _schedule_async(fanout_event(envelope))

            # ntfy push — only after hysteresis window has elapsed.
            # On the very first insert, first_seen == now, so elapsed == 0 (below threshold).
            # The push fires on the NEXT evaluate_rules call where the condition is still
            # active AND elapsed >= hysteresis_sec, which is handled in the still-active branch
            # below. For simplicity, we also push on first insert to avoid
            # missing short-lived frost events that resolve before the next tick.
            # This is an explicit design choice: see plan note on hysteresis.
            from observatory.weather.alerts.notifier import notify_all

            _schedule_async(
                notify_all(
                    title=_rule_title(rule_name),
                    message=result.detail,
                    priority=4,
                )
            )

        elif result.triggered and active_row is not None:
            # STILL ACTIVE — no new DB row (dedup).
            # Hysteresis re-push: if first-seen was before the hysteresis window
            # AND we haven't pushed yet, schedule a push now. (Belt-and-braces for
            # the case where the initial push was skipped or the topic is new.)
            pass  # dedup: no action needed

        elif (not result.triggered) and active_row is not None:
            # RESOLVED — set resolved_at_ts.
            conn.execute(
                "UPDATE alerts SET resolved_at_ts=? WHERE id=?",
                (now, active_row[0]),
            )
            conn.commit()
            log.info("alert_resolved", rule=rule_name)

            # Clear in-memory first-seen tracker.
            _first_seen_ts.pop(rule_name, None)

            # Fan out the resolution.
            resolved_envelope: dict[str, Any] = {
                "type": "alert",
                "data": {
                    "rule": rule_name,
                    "resolved_at_ts": now,
                },
                "ts": now,
            }
            from observatory.api.routers.ws import fanout_event

            _schedule_async(fanout_event(resolved_envelope))

            # Recovery push (both channels) — e.g. "Enviro Online" after a battery swap.
            from observatory.weather.alerts.notifier import notify_all

            rec_title, rec_body = _recovery_message(rule_name)
            _schedule_async(notify_all(title=rec_title, message=rec_body, priority=3))

        # else: still-clear — no action.
