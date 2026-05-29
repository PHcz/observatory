"""Pipeline A: MQTT subscriber → SQLite write integration (QA-02).

Publishes one Pimoroni-shaped envelope to the testcontainers Mosquitto and
asserts the real ``observatory.weather.subscriber.run_subscriber`` writes
the matching row into the tmp SQLite via ``write_reading``.

Field-alias note: the firmware uses ``luminance`` (not ``light``); confirmed
against the real firmware on 2026-05-28 — see ``observatory/weather/payload.py``
module docstring.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

import aiomqtt
import pytest


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pipeline_a_mqtt_to_sqlite(
    integration_settings: None,
    broker_host_port: tuple[str, int],
    tmp_db_with_migrations: Path,
) -> None:
    # Import after integration_settings rebinds settings — subscriber's
    # module-level ``settings`` and ``write_reading`` import is now the
    # tmp-DB-bound instance.
    from observatory.config import settings
    from observatory.weather.subscriber import run_subscriber

    host, port = broker_host_port
    stop_event = asyncio.Event()

    # Pass tmp DB explicitly so writer hits the migrated tmp file even if
    # any code path bypasses the settings rebind.
    subscriber_task = asyncio.create_task(
        run_subscriber(stop_event, db_path=str(tmp_db_with_migrations))
    )
    # Give the subscriber time to connect + subscribe.
    await asyncio.sleep(1.0)

    nickname = settings.weather_nickname
    payload = {
        "nickname": nickname,
        "timestamp": "2026-05-28T12:00:00Z",
        "readings": {
            "temperature": 18.4,
            "humidity": 62.0,
            "pressure": 1013.2,
            "luminance": 5500.0,
            "voltage": 3.1,
        },
    }

    try:
        async with aiomqtt.Client(hostname=host, port=port) as pub:
            await pub.publish(
                f"enviro/{nickname}",
                payload=json.dumps(payload).encode("utf-8"),
                qos=1,
            )

        # Poll the DB up to 5s for the inserted row.
        deadline = asyncio.get_event_loop().time() + 5.0
        row: tuple[str, float, float, float, float] | None = None
        while asyncio.get_event_loop().time() < deadline:
            conn = sqlite3.connect(str(tmp_db_with_migrations))
            try:
                cursor = conn.execute(
                    "SELECT node_id, temp_c, humidity_pct, pressure_hpa, lux FROM weather LIMIT 1"
                )
                row = cursor.fetchone()
            finally:
                conn.close()
            if row is not None:
                break
            await asyncio.sleep(0.1)
    finally:
        stop_event.set()
        try:
            await asyncio.wait_for(subscriber_task, timeout=5.0)
        except (TimeoutError, asyncio.CancelledError):
            subscriber_task.cancel()

    assert row is not None, "weather row did not appear in DB within 5 seconds"
    assert row[0] == nickname
    assert row[1] == pytest.approx(18.4)
    assert row[2] == pytest.approx(62.0)
    assert row[3] == pytest.approx(1013.2)
    assert row[4] == pytest.approx(5500.0)
