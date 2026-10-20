"""MQTT broker hardening (security audit 2026-10-20, F17/F19/F20).

F17: obs-api's subscribers used fixed, public client ids. MQTT lets a new
connection with an existing client id kick the old one off, so anyone holding
ANY broker credential -- the outdoor board's sits in the garden -- could keep
the dashboard's ingestion permanently disconnected.
F19: no packet-size cap. F20: any room id from indoor-node was accepted.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr

from observatory.indoor.topic import parse_metric_topic
from observatory.mqtt_identity import client_identifier

REPO_ROOT = Path(__file__).resolve().parent.parent
MOSQUITTO_CONF = (REPO_ROOT / "deploy" / "mosquitto" / "mosquitto.conf").read_text()


def test_client_id_is_stable_for_the_same_password() -> None:
    assert client_identifier("weather", SecretStr("pw")) == client_identifier(
        "weather", SecretStr("pw")
    )


def test_client_id_cannot_be_guessed_without_the_password() -> None:
    a = client_identifier("weather", SecretStr("pw-one"))
    b = client_identifier("weather", SecretStr("pw-two"))
    assert a != b
    assert a not in ("obs-api-weather-sub", "obs-api-indoor-sub")
    assert "pw-one" not in a


def test_client_ids_differ_per_subscriber() -> None:
    pw = SecretStr("pw")
    assert client_identifier("weather", pw) != client_identifier("indoor", pw)


def test_client_id_fits_the_mqtt_311_limit() -> None:
    assert len(client_identifier("indoor", SecretStr("x" * 200))) <= 23


def test_subscribers_use_the_derived_client_ids() -> None:
    for mod in ("weather", "indoor"):
        src = (REPO_ROOT / "observatory" / mod / "subscriber.py").read_text()
        assert "client_identifier(" in src
        assert "_CLIENT_IDENTIFIER" not in src


@pytest.mark.parametrize("directive", ["max_packet_size 65536", "persistent_client_expiration 14d"])
def test_broker_limits(directive: str) -> None:
    assert directive in MOSQUITTO_CONF


@pytest.mark.parametrize("node", ["Living-Room", "a" * 33, "room.1", "x y", "-room", "%2e%2e"])
def test_malformed_room_ids_are_dropped(node: str) -> None:
    assert parse_metric_topic(f"indoor/{node}/sensor/co2/state") is None


def test_wellformed_room_id_parses() -> None:
    parsed = parse_metric_topic("indoor/living-room/sensor/co2/state")
    assert parsed is not None and parsed.node_id == "living-room"


def test_room_allowlist_when_configured() -> None:
    allowed = frozenset({"living-room"})
    assert parse_metric_topic("indoor/living-room/sensor/co2/state", allowed) is not None
    assert parse_metric_topic("indoor/garage/sensor/co2/state", allowed) is None
