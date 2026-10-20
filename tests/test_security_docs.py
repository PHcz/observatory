"""Security docs describe the system as it actually is (security audit C7/F21/F30).

SECURITY.md claimed services were "bound to the LAN interface only" while the
API bound the dual-stack wildcard; .env.example still recommended the retired
API_BIND_HOST=auto; nothing said MQTT is plaintext on the wifi.
"""

from __future__ import annotations

import re
from pathlib import Path

from observatory.config import Settings

REPO_ROOT = Path(__file__).resolve().parent.parent
SECURITY = (REPO_ROOT / "SECURITY.md").read_text()
ENV_EXAMPLE = (REPO_ROOT / ".env.example").read_text()


def _example_value(key: str) -> str:
    m = re.search(rf"^{key}=(.*)$", ENV_EXAMPLE, re.M)
    assert m, f"{key} missing from .env.example"
    return m.group(1).strip()


def test_env_example_bind_host_matches_the_real_default() -> None:
    assert _example_value("API_BIND_HOST") == Settings.model_fields["api_bind_host"].default


def test_env_example_allowlist_matches_the_real_default() -> None:
    default = Settings.model_fields["api_origin_allowlist"].default
    assert _example_value("API_ORIGIN_ALLOWLIST") == default


def test_security_md_states_the_enforced_boundary() -> None:
    assert "bound to the LAN interface only" not in SECURITY
    for fact in ("nftables", "Host", "Origin", "plaintext", "ntfy"):
        assert fact in SECURITY, f"SECURITY.md should cover {fact}"


def _rotation_section() -> str:
    ops = (REPO_ROOT / "docs" / "OPERATIONS.md").read_text()
    start = ops.find("## Secrets & rotation")
    assert start != -1, "docs/OPERATIONS.md needs a '## Secrets & rotation' section"
    end = ops.find("\n## ", start + 1)
    return ops[start : end if end != -1 else None]


def test_every_secret_setting_has_a_rotation_entry() -> None:
    """Audit M9: no secret-lifecycle documentation existed. Every SecretStr
    setting must say where it lives and how to rotate it."""
    from pydantic import SecretStr

    section = _rotation_section()
    secret_fields = [n for n, f in Settings.model_fields.items() if f.annotation is SecretStr]
    assert secret_fields
    for name in secret_fields:
        assert name.upper() in section, f"{name.upper()} missing from Secrets & rotation"


def test_rotation_covers_a_compromised_outdoor_board() -> None:
    """Accepted risk (2026-10-20): the board holds the home wifi password and
    reveals it in provisioning mode. The recovery must be written down -- and
    the Pi itself is on wifi, so its stored password must change FIRST."""
    section = _rotation_section()
    assert "lost or tampered" in section
    assert "nmcli" in section and "mosquitto_passwd" in section
    pi_step = section.find("nmcli")
    hub_step = section.find("on the Hub")
    assert -1 < pi_step < hub_step, "update the Pi's stored wifi password before the Hub's"
