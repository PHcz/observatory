"""aiomqtt subscriber loop for Pimoroni Enviro Weather (Phase 3-03).

Lives in the FastAPI lifespan as an asyncio background task (wiring is
Plan 03-04's job). Reconnect-on-MqttError with exponential backoff capped
at ``settings.weather_subscriber_backoff_max_sec``. Strict-nickname filter
drops messages from any nickname other than ``settings.weather_nickname``.

QoS 1 is declared on the subscribe call even though Pimoroni firmware
publishes QoS 0 — the effective QoS is ``min(pub, sub) = 0``, but declaring
1 documents intent and is correct for any future firmware patch that
raises publisher QoS (see 03-RESEARCH §Pitfall 3).

Backoff implemented via ``asyncio.wait_for(stop_event.wait(), timeout=...)``
rather than ``asyncio.sleep`` so a fresh stop_event.set() during the
backoff window exits the loop cleanly instead of waiting the full interval.
"""

from __future__ import annotations

import asyncio

import aiomqtt
import structlog
from pydantic import ValidationError

from observatory.config import settings
from observatory.weather.payload import parse_envelope
from observatory.weather.writer import write_reading

log = structlog.get_logger(__name__)

_CLIENT_IDENTIFIER = "obs-api-weather-sub"


def _topic_str(message: aiomqtt.Message) -> str:
    """Best-effort string form of message.topic across aiomqtt 2.x variants."""
    t = getattr(message, "topic", None)
    if t is None:
        return ""
    return str(getattr(t, "value", t))


async def _handle_message(message: aiomqtt.Message, db_path: str | None) -> None:
    """Parse one MQTT message and dispatch to writer. Never raises.

    Routing:
      1. parse_envelope → on JSON/schema failure, log WARN
         event=weather_payload_invalid and drop.
      2. Nickname filter — only ``settings.weather_nickname`` is persisted;
         everything else logs WARN event=weather_nickname_unknown and is
         dropped (strict allowlist per 03-CONTEXT §Unknown-nickname handling).
      3. asyncio.to_thread(write_reading, ...) — keeps the event loop snappy
         while the synchronous sqlite3 INSERT runs in the default executor.
    """
    try:
        envelope = parse_envelope(message.payload)
    except ValidationError as exc:
        log.warning(
            "weather_payload_invalid",
            topic=_topic_str(message),
            error=str(exc)[:200],
        )
        return
    except Exception as exc:  # invalid JSON / decode errors
        log.warning(
            "weather_payload_invalid",
            topic=_topic_str(message),
            error=str(exc)[:200],
        )
        return

    if envelope.nickname != settings.weather_nickname:
        log.warning(
            "weather_nickname_unknown",
            nickname=envelope.nickname,
            expected=settings.weather_nickname,
        )
        return

    # Run blocking sqlite3 in default executor — keeps event loop snappy.
    await asyncio.to_thread(write_reading, envelope, db_path)


async def run_subscriber(
    stop_event: asyncio.Event,
    db_path: str | None = None,
) -> None:
    """Long-running async subscriber. Loop exits cleanly when stop_event.set().

    Reconnects on aiomqtt.MqttError with exponential backoff between
    ``settings.weather_subscriber_backoff_initial_sec`` and
    ``settings.weather_subscriber_backoff_max_sec``. Resets to initial
    on a successful connect/subscribe.
    """
    interval = settings.weather_subscriber_backoff_initial_sec
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
                await client.subscribe(settings.weather_mqtt_topic_filter, qos=1)
                log.info(
                    "weather_mqtt_subscribed",
                    topic=settings.weather_mqtt_topic_filter,
                    broker=f"{settings.mqtt_broker_host}:{settings.mqtt_broker_port}",
                )
                interval = settings.weather_subscriber_backoff_initial_sec  # reset on success
                async for message in client.messages:
                    if stop_event.is_set():
                        break
                    await _handle_message(message, db_path)
        except aiomqtt.MqttError as exc:
            log.warning(
                "weather_mqtt_disconnected",
                error=str(exc),
                retry_in_sec=interval,
            )
            # wait_for(stop_event) during backoff — fires immediately if
            # stop_event.set() during the wait, instead of sleeping the full
            # interval and only exiting on the next loop check.
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
                break  # stop_event fired during backoff — exit cleanly
            except TimeoutError:
                pass
            interval = min(
                interval * 2,
                settings.weather_subscriber_backoff_max_sec,
            )
        except asyncio.CancelledError:
            log.info("weather_mqtt_loop_cancelled")
            raise
    log.info("weather_mqtt_loop_stopped")
