"""MQTT client ids for obs-api's subscribers (security audit 2026-10-20, F17).

MQTT disconnects an existing session when a new client connects with the same
id. With fixed, public ids, anyone holding ANY broker credential -- the
outdoor board's sits in a garden -- could keep obs-api's subscribers knocked
offline. The id therefore carries a suffix derived from obs-api's own MQTT
password: stable across restarts (so the persistent session and its queued
QoS-1 messages survive), unguessable without that password.
"""

from __future__ import annotations

import hashlib
import hmac

from pydantic import SecretStr

# MQTT 3.1.1 only guarantees 23-character client ids.
_MAX_LEN = 23


def client_identifier(role: str, password: SecretStr) -> str:
    """Return ``obs-<role>-<hmac>`` for one subscriber role (e.g. "weather")."""
    digest = hmac.new(
        password.get_secret_value().encode(), f"mqtt-client-id:{role}".encode(), hashlib.sha256
    ).hexdigest()
    prefix = f"obs-{role}-"
    return prefix + digest[: _MAX_LEN - len(prefix)]
