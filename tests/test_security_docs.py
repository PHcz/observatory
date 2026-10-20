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
