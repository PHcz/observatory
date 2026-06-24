"""Daily Enviro heartbeat — pure-function tests for build_message()."""

from __future__ import annotations

from typing import Any

from observatory.ops.enviro_heartbeat import build_message

NOW = 1_700_000_000
STALE = 3600  # 1 h threshold


def _stats(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"last_ts": NOW - 120, "count_24h": 270}
    base.update(kw)
    return base


def test_healthy_message() -> None:
    msg = build_message(_stats(temp_c=19.2, humidity_pct=64.0, pressure_hpa=1017.4), NOW, STALE)
    assert msg.startswith("✅ Enviro health: online")
    assert "Last reading: 2 m ago" in msg
    assert "Readings in 24 h: 270" in msg
    assert "19.2°C, 64% RH, 1017 hPa" in msg


def test_stale_message_flags_warning_but_still_reports() -> None:
    msg = build_message(_stats(last_ts=NOW - 2 * 3600), NOW, STALE)
    assert msg.startswith("⚠️ Enviro health: STALE")
    assert "Last reading: 2 h ago" in msg


def test_no_data_message() -> None:
    msg = build_message({"last_ts": None, "count_24h": 0}, NOW, STALE)
    assert "no weather data on record yet" in msg


def test_missing_values_omits_now_line() -> None:
    # temp/pressure absent → no "Now:" line, but still healthy + count.
    msg = build_message(_stats(temp_c=None, pressure_hpa=None), NOW, STALE)
    assert "Now:" not in msg
    assert msg.startswith("✅ Enviro health: online")
