"""The MQTT ACL must grant what the code and firmware need -- and no more.

Security audit 2026-10-20 (M11, F22/F50/C6): the repo's acl.conf had drifted
from the live broker. It lacked the indoor-node user and obs-api's read on
indoor/#, so a fresh bootstrap would have silently broken indoor ingestion --
and the old test (which only checked that two users were present) passed
throughout. Requirements here are DERIVED from config and firmware, not
restated, so the ACL cannot drift from what is actually used again.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ACL = REPO_ROOT / "deploy" / "mosquitto" / "acl.conf"
README = REPO_ROOT / "deploy" / "mosquitto" / "README.md"
INDOOR_SECRETS_EXAMPLE = REPO_ROOT / "firmware" / "indoor-air" / "secrets.yaml.example"
ENVIRO_USER = "enviro-observatory-weather"


def _grants() -> dict[str, list[tuple[str, str]]]:
    grants: dict[str, list[tuple[str, str]]] = {}
    user = None
    for raw in ACL.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("user "):
            user = line.split(None, 1)[1]
            grants.setdefault(user, [])
        elif line.startswith("topic ") and user is not None:
            _, access, pattern = line.split(None, 2)
            grants[user].append((access, pattern))
    return grants


def _matches(pattern: str, topic: str) -> bool:
    """MQTT wildcard match ('#' multi-level, '+' single-level)."""
    p, t = pattern.split("/"), topic.split("/")
    for i, seg in enumerate(p):
        if seg == "#":
            return True
        if i >= len(t) or (seg != "+" and seg != t[i]):
            return False
    return len(p) == len(t)


def _can(user: str, access: str, topic: str) -> bool:
    return any(
        a in (access, "readwrite") and _matches(pat, topic) for a, pat in _grants().get(user, [])
    )


def test_api_subscriber_can_read_every_feed_it_subscribes_to() -> None:
    from observatory.config import Settings

    fields = Settings.model_fields
    user = fields["mqtt_username"].default
    for name in ("weather_mqtt_topic_filter", "indoor_mqtt_topic_filter"):
        topic_filter = fields[name].default
        assert _can(user, "read", topic_filter), f"{user} cannot read {topic_filter} ({name})"


def test_indoor_firmware_user_can_publish() -> None:
    m = re.search(r'^mqtt_user:\s*"([^"]+)"', INDOOR_SECRETS_EXAMPLE.read_text(), re.M)
    assert m, "mqtt_user missing from the indoor firmware secrets example"
    assert _can(m.group(1), "write", "indoor/living-room/sensor/co2/state")


def test_enviro_publisher_can_publish() -> None:
    assert _can(ENVIRO_USER, "write", "enviro/observatory-weather")


def test_least_privilege() -> None:
    """Publishers never read; the API subscriber never writes."""
    from observatory.config import Settings

    subscriber = Settings.model_fields["mqtt_username"].default
    for user, entries in _grants().items():
        accesses = {a for a, _ in entries}
        if user in XMAS_GRANTS:
            continue  # the lights project's own users: see test_xmas_users_*
        if user in (subscriber, HEALTH_USER):
            assert accesses == {"read"}, f"{user} should only read: {entries}"
        else:
            assert accesses == {"write"}, f"publisher {user} should only write: {entries}"


def test_every_acl_user_is_in_the_password_instructions() -> None:
    """An ACL user nobody is told to create a password for cannot connect."""
    readme = README.read_text()
    for user in _grants():
        assert user in readme, f"{user} has ACL grants but no mosquitto_passwd instruction"


# --- Health monitor for the xmas-lights project (2026-11-14) -----------------
# A second project on the same Pi proves, before and after each of its hardware
# steps, that the observatory loses no MQTT messages. It gets its own read-only
# user: broker statistics plus one fixed-interval and one irregular topic. It can
# never publish, so it can never inject or overwrite observatory data.

HEALTH_USER = "xmas-health"
HEALTH_TOPICS = (
    "$SYS/broker/uptime",
    "$SYS/broker/publish/messages/received",
    "$SYS/broker/publish/messages/dropped",
    "indoor/living-room/sensor/co2/state",
    "enviro/observatory-weather",
)


def test_health_monitor_reads_only_what_it_needs() -> None:
    entries = _grants()[HEALTH_USER]
    assert {a for a, _ in entries} == {"read"}, f"{HEALTH_USER} must only read: {entries}"
    for topic in HEALTH_TOPICS:
        assert _can(HEALTH_USER, "read", topic), topic
    for topic in ("indoor/living-room/sensor/temperature/state", "indoor/#", "#"):
        assert not _can(HEALTH_USER, "read", topic), f"{HEALTH_USER} should not read {topic}"
    for topic in ("enviro/observatory-weather", "indoor/living-room/sensor/co2/state"):
        assert not _can(HEALTH_USER, "write", topic)


# --- Christmas lights project users (2026-11-17) ------------------------------
# The second project on this Pi runs its own MQTT clients on the shared broker.
# Exact topics only, all under xmas/ -- they can never read or write an
# observatory topic. Requested by the xmas-lights session with the owner's yes.

XMAS_GRANTS: dict[str, set[tuple[str, str]]] = {
    "xmas-display": {
        ("read", "xmas/scene"),
        ("read", "xmas/color"),
        ("read", "xmas/brightness"),
        ("read", "xmas/power"),
        ("write", "xmas/status"),  # includes its last will
        ("read", "xmas/voice/heard"),  # Phase 5 voice code words (2026-11-20)
        ("read", "xmas/voice/status"),
    },
    "xmas-remote": {
        ("write", "xmas/scene"),
        ("write", "xmas/color"),
        ("write", "xmas/brightness"),
        ("write", "xmas/power"),
        ("read", "xmas/status"),
    },
    "xmas-voice": {
        ("write", "xmas/voice/heard"),
        ("write", "xmas/voice/status"),
        ("read", "xmas/status"),
    },
}


def test_xmas_users_have_exactly_the_requested_rules() -> None:
    grants = _grants()
    for user, wanted in XMAS_GRANTS.items():
        assert set(grants.get(user, [])) == wanted, user


def test_xmas_users_stay_inside_their_prefix() -> None:
    for user in XMAS_GRANTS:
        for access, pattern in _grants().get(user, []):
            assert pattern.startswith("xmas/"), f"{user} has {access} on {pattern}"
            assert "#" not in pattern and "+" not in pattern, f"{user}: wildcard {pattern}"
            assert access in ("read", "write"), f"{user}: {access} on {pattern}"


def test_no_observatory_user_touches_xmas_topics() -> None:
    for user, entries in _grants().items():
        if user in XMAS_GRANTS:
            continue
        for _access, pattern in entries:
            assert not pattern.startswith("xmas/"), f"{user} reaches {pattern}"
