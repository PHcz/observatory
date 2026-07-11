"""Daily Enviro heartbeat — pure-function tests for build_message()."""

from __future__ import annotations

from typing import Any

from observatory.ops.enviro_heartbeat import (
    _co2_band,
    build_indoor_message,
    build_message,
)

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


# --- indoor block ---------------------------------------------------------


def _node(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "node_id": "living-room",
        "last_ts": NOW - 60,
        "co2_ppm": 451,
        "temp_c": 21.3,
        "humidity_pct": 48.0,
        "pressure_hpa": 1019.2,
        "count_24h": 288,
    }
    base.update(kw)
    return base


def test_co2_band_boundaries() -> None:
    assert _co2_band(799) == "Fresh"
    assert _co2_band(800) == "Stuffy"
    assert _co2_band(1199) == "Stuffy"
    assert _co2_band(1200) == "Ventilate"


def test_no_indoor_node_omits_block() -> None:
    assert build_indoor_message([], NOW) is None


def test_indoor_block_healthy() -> None:
    msg = build_indoor_message([_node()], NOW)
    assert msg is not None
    assert msg.startswith("✅ Indoor · living room: online")
    assert "Last reading: 1 m ago" in msg
    assert "Readings in 24 h: 288" in msg
    assert "Now: CO₂ 451 ppm (Fresh), 21.3°C, 48% RH, 1019 hPa" in msg


def test_indoor_block_stale_flags_warning() -> None:
    msg = build_indoor_message([_node(last_ts=NOW - 2 * 3600)], NOW, stale_sec=900)
    assert msg is not None
    assert msg.startswith("⚠️ Indoor · living room: STALE")


def test_indoor_block_red_co2_verdict() -> None:
    msg = build_indoor_message([_node(co2_ppm=1450)], NOW)
    assert msg is not None
    assert "CO₂ 1450 ppm (Ventilate)" in msg


def test_indoor_block_multi_node() -> None:
    msg = build_indoor_message([_node(), _node(node_id="bedroom", co2_ppm=900)], NOW)
    assert msg is not None
    assert "Indoor · living room" in msg
    assert "Indoor · bedroom" in msg
    assert "CO₂ 900 ppm (Stuffy)" in msg
    # two sections separated by a blank line
    assert msg.count("Readings in 24 h:") == 2
