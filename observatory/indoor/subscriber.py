"""aiomqtt subscriber for the indoor air node(s) (Phase 14 INDOOR-03).

Runs inside obs-api's lifespan as an asyncio task, alongside the weather
subscriber, on the same broker connection settings. Subscribes to
``settings.indoor_mqtt_topic_filter`` (default ``indoor/#``) and coalesces the
ESPHome per-sensor messages into one ``indoor_air`` row per node per cycle.

Coalescing (IndoorAggregator): ESPHome publishes co2/temperature/humidity/
pressure as four separate messages in a tight burst each ~60s. Rather than
write four partial rows, we buffer per node and flush a single row once
``settings.indoor_flush_debounce_sec`` passes with no further metric for that
node — order-independent and robust to a missing/extra metric.

Reconnect-on-MqttError with the same exponential backoff as the weather
subscriber; loop exits cleanly on ``stop_event.set()``.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

import aiomqtt
import structlog

from observatory.config import settings
from observatory.indoor.topic import coerce_value, parse_metric_topic
from observatory.indoor.writer import write_reading

log = structlog.get_logger(__name__)

_CLIENT_IDENTIFIER = "obs-api-indoor-sub"

# node_id, {column: value} → persist. Injectable so tests avoid a real DB.
FlushFn = Callable[[str, "dict[str, float | int]"], Awaitable[None]]

# Explicit re-exports (mypy --strict no-implicit-reexport) so tests can
# monkeypatch these module attributes.
__all__ = [
    "IndoorAggregator",
    "run_indoor_subscriber",
    "settings",
    "write_reading",
]


class IndoorAggregator:
    """Buffer per-node metrics and debounce-flush them as one row."""

    def __init__(self, flush: FlushFn, debounce_sec: float) -> None:
        self._flush = flush
        self._debounce = debounce_sec
        self._pending: dict[str, dict[str, float | int]] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def ingest(self, node_id: str, column: str, value: float | int) -> None:
        """Record one metric and (re)arm this node's debounce timer."""
        self._pending.setdefault(node_id, {})[column] = value
        existing = self._tasks.get(node_id)
        if existing is not None and not existing.done():
            existing.cancel()
        self._tasks[node_id] = asyncio.create_task(self._debounced_flush(node_id))

    async def _debounced_flush(self, node_id: str) -> None:
        try:
            await asyncio.sleep(self._debounce)
        except asyncio.CancelledError:
            return
        values = self._pending.pop(node_id, {})
        self._tasks.pop(node_id, None)
        if values:
            await self._flush(node_id, dict(values))

    async def flush_all(self) -> None:
        """Cancel pending timers and flush any buffered readings (shutdown)."""
        for node_id in list(self._tasks):
            task = self._tasks.pop(node_id, None)
            if task is not None and not task.done():
                task.cancel()
        for node_id in list(self._pending):
            values = self._pending.pop(node_id, {})
            if values:
                await self._flush(node_id, dict(values))


def _topic_str(message: aiomqtt.Message) -> str:
    """Best-effort string form of message.topic across aiomqtt 2.x variants."""
    t = getattr(message, "topic", None)
    if t is None:
        return ""
    return str(getattr(t, "value", t))


def _payload_str(message: aiomqtt.Message) -> str:
    payload = message.payload
    if isinstance(payload, bytes | bytearray):
        try:
            return payload.decode()
        except UnicodeDecodeError:
            return ""
    return str(payload)


async def _handle_message(message: aiomqtt.Message, aggregator: IndoorAggregator) -> None:
    """Parse one MQTT message and feed the aggregator. Never raises."""
    parsed = parse_metric_topic(_topic_str(message))
    if parsed is None:
        return  # status / debug / unknown metric — ignore
    value = coerce_value(parsed.column, _payload_str(message))
    if value is None:
        return  # NaN / unparseable — leave that column NULL this cycle
    aggregator.ingest(parsed.node_id, parsed.column, value)


async def run_indoor_subscriber(stop_event: asyncio.Event, db_path: str | None = None) -> None:
    """Long-running async indoor subscriber; exits cleanly on stop_event.set()."""

    async def flush(node_id: str, values: dict[str, float | int]) -> None:
        ts = int(time.time())
        await asyncio.to_thread(write_reading, node_id, ts, values, db_path)

    aggregator = IndoorAggregator(flush, settings.indoor_flush_debounce_sec)
    interval = settings.weather_subscriber_backoff_initial_sec
    try:
        while not stop_event.is_set():
            try:
                async with aiomqtt.Client(
                    hostname=settings.mqtt_broker_host,
                    port=settings.mqtt_broker_port,
                    username=settings.mqtt_username or None,
                    password=settings.mqtt_password or None,
                    identifier=_CLIENT_IDENTIFIER,
                    clean_session=False,
                    keepalive=60,
                ) as client:
                    await client.subscribe(settings.indoor_mqtt_topic_filter, qos=1)
                    log.info(
                        "indoor_mqtt_subscribed",
                        topic=settings.indoor_mqtt_topic_filter,
                        broker=f"{settings.mqtt_broker_host}:{settings.mqtt_broker_port}",
                    )
                    interval = settings.weather_subscriber_backoff_initial_sec
                    async for message in client.messages:
                        if stop_event.is_set():
                            break
                        await _handle_message(message, aggregator)
            except aiomqtt.MqttError as exc:
                log.warning("indoor_mqtt_disconnected", error=str(exc), retry_in_sec=interval)
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=interval)
                    break
                except TimeoutError:
                    pass
                interval = min(interval * 2, settings.weather_subscriber_backoff_max_sec)
    except asyncio.CancelledError:
        log.info("indoor_mqtt_loop_cancelled")
        raise
    finally:
        await aggregator.flush_all()
    log.info("indoor_mqtt_loop_stopped")
