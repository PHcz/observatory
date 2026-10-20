"""Host firewall for the Pi (security audit 2026-10-20, H2).

"No port forwarding" was a router setting, not a control: the Hub's UPnP IGD is
live, the Pi had no firewall, and the API binds every interface. Any
compromised LAN device could map the internet to :8000 or :22. These tests pin
the property that matters -- every service port is reachable only from the LAN
-- not merely that a ruleset file exists.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RULES = REPO_ROOT / "deploy" / "nftables" / "observatory.nft"
BOOTSTRAP = REPO_ROOT / "scripts" / "bootstrap-pi.sh"
SERVICE_PORTS = ("22", "8000", "1883")


def _rule_lines() -> list[str]:
    return [
        ln.strip()
        for ln in RULES.read_text().splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]


def _chain(name: str) -> str:
    text = RULES.read_text()
    m = re.search(rf"chain {name} \{{(.*?)\n    \}}", text, re.S)
    assert m, f"chain {name} not found"
    return m.group(1)


def test_input_and_forward_default_to_drop() -> None:
    assert "policy drop" in _chain("input")
    assert "policy drop" in _chain("forward")


def test_every_service_port_is_source_restricted() -> None:
    """No rule may accept a service port without pinning the source to the LAN."""
    for line in _rule_lines():
        if "accept" not in line or "dport" not in line:
            continue
        opens_service = any(re.search(rf"\b{p}\b", line) for p in SERVICE_PORTS)
        if opens_service:
            assert "saddr @lan_v4" in line or "saddr fe80::/10" in line, (
                f"service port opened without a LAN source restriction: {line!r}"
            )


def test_keeps_ipv6_neighbour_discovery_working() -> None:
    """Dropping ICMPv6 silently breaks IPv6 -- and the Mac reaches the Pi over it."""
    assert "meta l4proto ipv6-icmp accept" in _chain("input")


def test_lan_subnet_is_filled_in_at_install_not_hardcoded() -> None:
    assert "@LAN_V4_NET@" in RULES.read_text()


def test_bootstrap_installs_and_enables_the_firewall() -> None:
    b = BOOTSTRAP.read_text()
    assert "deploy/nftables/observatory.nft" in b
    assert "@LAN_V4_NET@" in b, "bootstrap must substitute the detected LAN subnet"
    assert "systemctl enable nftables.service" in b


def test_bootstrap_pins_ipv6_to_link_local() -> None:
    """A future ISP IPv6 rollout must not hand the Pi a public address silently."""
    assert "ipv6.method link-local" in BOOTSTRAP.read_text()
