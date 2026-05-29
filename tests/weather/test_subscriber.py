"""TDD tests for the aiomqtt subscriber loop (Phase 3-03).

The subscriber module exposes a private `_handle_message(message, db_path)`
helper that tests invoke directly with fabricated message objects — this
isolates the routing/filter/error-handling logic from aiomqtt's async
context machinery.

For the connection-loop tests, a minimal `FakeMqttClient` test double
emulates aiomqtt.Client (__aenter__, __aexit__, subscribe, .messages
async iterator). Injected via monkeypatch on
`observatory.weather.subscriber.aiomqtt.Client`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar

import aiomqtt
import pytest
from structlog.testing import capture_logs

from observatory.weather import subscriber as sub_mod


def _msg(payload_bytes: bytes, topic: str = "enviro/observatory-weather") -> Any:
    """Fabricate a minimal aiomqtt.Message-like object (topic.value + payload)."""
    return SimpleNamespace(
        payload=payload_bytes,
        topic=SimpleNamespace(value=topic),
    )


# ---------------------------------------------------------------------------
# _handle_message tests (routing / filter / error handling)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_message_canonical_writes_row(
    tmp_db: Path,
    load_payload: Callable[[str], bytes],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, float]] = []

    def _writer(env: Any, db_path: str | None = None) -> bool:
        calls.append((env.nickname, env.readings.temp_c))
        return True

    monkeypatch.setattr(sub_mod, "write_reading", _writer)
    monkeypatch.setattr(sub_mod.settings, "weather_nickname", "observatory-weather")
    await sub_mod._handle_message(_msg(load_payload("canonical_payload.json")), str(tmp_db))
    assert calls == [("observatory-weather", 18.4)]


@pytest.mark.asyncio
async def test_handle_message_unknown_nickname_dropped(
    tmp_db: Path,
    load_payload: Callable[[str], bytes],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    def _record_call(*a: object, **k: object) -> bool:
        calls.append(1)
        return True

    monkeypatch.setattr(sub_mod, "write_reading", _record_call)
    monkeypatch.setattr(sub_mod.settings, "weather_nickname", "observatory-weather")
    with capture_logs() as logs:
        await sub_mod._handle_message(_msg(load_payload("unknown_nickname.json")), str(tmp_db))
    assert calls == []
    assert any(
        e.get("event") == "weather_nickname_unknown" and e.get("nickname") == "rogue-device"
        for e in logs
    )


@pytest.mark.asyncio
async def test_handle_message_malformed_logged_dropped(
    tmp_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    def _record_call(*a: object, **k: object) -> bool:
        calls.append(1)
        return True

    monkeypatch.setattr(sub_mod, "write_reading", _record_call)
    monkeypatch.setattr(sub_mod.settings, "weather_nickname", "observatory-weather")
    with capture_logs() as logs:
        await sub_mod._handle_message(_msg(b"not json"), str(tmp_db))
    assert calls == []
    assert any(e.get("event") == "weather_payload_invalid" for e in logs)


@pytest.mark.asyncio
async def test_handle_message_no_readings_logged_dropped(
    tmp_db: Path,
    load_payload: Callable[[str], bytes],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    def _record_call(*a: object, **k: object) -> bool:
        calls.append(1)
        return True

    monkeypatch.setattr(sub_mod, "write_reading", _record_call)
    monkeypatch.setattr(sub_mod.settings, "weather_nickname", "observatory-weather")
    with capture_logs() as logs:
        await sub_mod._handle_message(_msg(load_payload("malformed_no_readings.json")), str(tmp_db))
    assert calls == []
    assert any(e.get("event") == "weather_payload_invalid" for e in logs)


# ---------------------------------------------------------------------------
# FakeMqttClient — minimal aiomqtt.Client test double
# ---------------------------------------------------------------------------


class FakeMqttClient:
    """Class-level state lets a test pre-program raise counts + collect calls."""

    raise_count: ClassVar[int] = 0  # number of __aenter__ calls that should raise
    subscribed: ClassVar[list[tuple[str, int]]] = []
    kwargs: ClassVar[dict[str, Any]] = {}
    messages_to_yield: ClassVar[list[Any]] = []
    instances_made: ClassVar[int] = 0

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        FakeMqttClient.kwargs = kwargs
        FakeMqttClient.instances_made += 1
        self._should_raise = FakeMqttClient.raise_count > 0
        if self._should_raise:
            FakeMqttClient.raise_count -= 1

    async def __aenter__(self) -> FakeMqttClient:
        if self._should_raise:
            raise aiomqtt.MqttError("simulated disconnect")
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def subscribe(self, topic: str, qos: int = 0) -> None:
        FakeMqttClient.subscribed.append((topic, qos))

    @property
    def messages(self) -> Any:
        msgs = list(FakeMqttClient.messages_to_yield)

        async def _gen() -> Any:
            for m in msgs:
                yield m
            # Exhausted — return rather than blocking. The subscriber's
            # outer `while not stop_event.is_set()` loop will spin: exit
            # async-with, re-enter, re-subscribe. The stopper task
            # eventually sets stop_event, which the outer loop checks.
            # Tiny sleep yields control so the test's stopper task runs.
            await asyncio.sleep(0.02)

        return _gen()


@pytest.fixture
def _reset_fake_client() -> None:
    FakeMqttClient.raise_count = 0
    FakeMqttClient.subscribed = []
    FakeMqttClient.kwargs = {}
    FakeMqttClient.messages_to_yield = []
    FakeMqttClient.instances_made = 0


# ---------------------------------------------------------------------------
# run_subscriber tests (loop control)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_subscriber_exits_on_stop_event(
    monkeypatch: pytest.MonkeyPatch,
    _reset_fake_client: None,
) -> None:
    monkeypatch.setattr(sub_mod.aiomqtt, "Client", FakeMqttClient)
    monkeypatch.setattr(sub_mod.settings, "weather_nickname", "observatory-weather")
    monkeypatch.setattr(sub_mod.settings, "weather_mqtt_topic_filter", "enviro/#")
    monkeypatch.setattr(sub_mod.settings, "weather_subscriber_backoff_initial_sec", 0.01)
    stop_event = asyncio.Event()

    async def _stopper() -> None:
        await asyncio.sleep(0.1)
        stop_event.set()

    await asyncio.wait_for(
        asyncio.gather(sub_mod.run_subscriber(stop_event), _stopper()),
        timeout=2.0,
    )


@pytest.mark.asyncio
async def test_run_subscriber_reconnects_on_mqtt_error(
    monkeypatch: pytest.MonkeyPatch,
    _reset_fake_client: None,
) -> None:
    FakeMqttClient.raise_count = 1  # first attempt raises, second succeeds
    monkeypatch.setattr(sub_mod.aiomqtt, "Client", FakeMqttClient)
    monkeypatch.setattr(sub_mod.settings, "weather_nickname", "observatory-weather")
    monkeypatch.setattr(sub_mod.settings, "weather_mqtt_topic_filter", "enviro/#")
    monkeypatch.setattr(sub_mod.settings, "weather_subscriber_backoff_initial_sec", 0.01)
    monkeypatch.setattr(sub_mod.settings, "weather_subscriber_backoff_max_sec", 0.05)
    stop_event = asyncio.Event()

    async def _stopper() -> None:
        await asyncio.sleep(0.3)
        stop_event.set()

    with capture_logs() as logs:
        await asyncio.wait_for(
            asyncio.gather(sub_mod.run_subscriber(stop_event), _stopper()),
            timeout=2.0,
        )

    # Reconnect log emitted at least once
    assert any(e.get("event") == "weather_mqtt_disconnected" for e in logs)
    # Both connection attempts happened (failed + succeeded)
    assert FakeMqttClient.instances_made >= 2


@pytest.mark.asyncio
async def test_subscribe_called_with_qos_1(
    monkeypatch: pytest.MonkeyPatch,
    _reset_fake_client: None,
) -> None:
    monkeypatch.setattr(sub_mod.aiomqtt, "Client", FakeMqttClient)
    monkeypatch.setattr(sub_mod.settings, "weather_nickname", "observatory-weather")
    monkeypatch.setattr(sub_mod.settings, "weather_mqtt_topic_filter", "enviro/#")
    monkeypatch.setattr(sub_mod.settings, "weather_subscriber_backoff_initial_sec", 0.01)
    stop_event = asyncio.Event()

    async def _stopper() -> None:
        await asyncio.sleep(0.1)
        stop_event.set()

    await asyncio.wait_for(
        asyncio.gather(sub_mod.run_subscriber(stop_event), _stopper()),
        timeout=2.0,
    )

    assert ("enviro/#", 1) in FakeMqttClient.subscribed
