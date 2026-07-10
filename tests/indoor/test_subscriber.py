"""Phase 14 INDOOR-03: indoor subscriber — aggregator debounce + message routing."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from observatory.indoor.subscriber import IndoorAggregator, _handle_message


def _msg(payload: bytes, topic: str) -> Any:
    """Minimal aiomqtt.Message-like object (topic.value + payload)."""
    return SimpleNamespace(payload=payload, topic=SimpleNamespace(value=topic))


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, float | int]]] = []

    async def flush(self, node_id: str, values: dict[str, float | int]) -> None:
        self.calls.append((node_id, dict(values)))


# ---- IndoorAggregator ----


async def test_metrics_coalesce_into_one_flush() -> None:
    rec = _Recorder()
    agg = IndoorAggregator(rec.flush, debounce_sec=0.05)
    agg.ingest("living-room", "co2_ppm", 822)
    agg.ingest("living-room", "temp_c", 21.4)
    agg.ingest("living-room", "humidity_pct", 39.2)
    agg.ingest("living-room", "pressure_hpa", 1017.1)
    await asyncio.sleep(0.15)
    assert rec.calls == [
        (
            "living-room",
            {"co2_ppm": 822, "temp_c": 21.4, "humidity_pct": 39.2, "pressure_hpa": 1017.1},
        )
    ]


async def test_separate_nodes_flush_separately() -> None:
    rec = _Recorder()
    agg = IndoorAggregator(rec.flush, debounce_sec=0.05)
    agg.ingest("a", "co2_ppm", 1)
    agg.ingest("b", "co2_ppm", 2)
    await asyncio.sleep(0.15)
    assert sorted(rec.calls) == [("a", {"co2_ppm": 1}), ("b", {"co2_ppm": 2})]


async def test_flush_all_flushes_pending_immediately() -> None:
    rec = _Recorder()
    agg = IndoorAggregator(rec.flush, debounce_sec=10.0)  # long: timer won't fire
    agg.ingest("a", "co2_ppm", 5)
    await agg.flush_all()
    assert rec.calls == [("a", {"co2_ppm": 5})]


# ---- _handle_message routing ----


async def test_handle_message_routes_sensor_metric() -> None:
    rec = _Recorder()
    agg = IndoorAggregator(rec.flush, debounce_sec=10.0)
    await _handle_message(_msg(b"822", "indoor/living-room/sensor/co2/state"), agg)
    await agg.flush_all()
    assert rec.calls == [("living-room", {"co2_ppm": 822})]


async def test_handle_message_ignores_status_and_debug() -> None:
    rec = _Recorder()
    agg = IndoorAggregator(rec.flush, debounce_sec=10.0)
    await _handle_message(_msg(b"online", "indoor/living-room/status"), agg)
    await _handle_message(_msg(b"[D][scd4x]", "indoor/living-room/debug"), agg)
    await agg.flush_all()
    assert rec.calls == []


async def test_handle_message_drops_nan_payload() -> None:
    rec = _Recorder()
    agg = IndoorAggregator(rec.flush, debounce_sec=10.0)
    await _handle_message(_msg(b"nan", "indoor/living-room/sensor/co2/state"), agg)
    await agg.flush_all()
    assert rec.calls == []
