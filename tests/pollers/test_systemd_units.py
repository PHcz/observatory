"""Smoke test: confirm all 6 systemd unit files exist with the right directives.

Verifies POLL-08 / SEC-05 / ROADMAP Criterion 5 statically — does NOT execute
systemd (the on-Pi acceptance in 04-06 covers runtime behavior).
"""

from __future__ import annotations

from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parents[2] / "deploy" / "systemd"

SOURCES = ["usgs", "emsc", "bgs"]
INTERVALS = {"usgs": "5min", "emsc": "5min", "bgs": "30min"}


@pytest.mark.parametrize("source", SOURCES)
def test_service_unit_exists(source: str) -> None:
    unit = DEPLOY / f"obs-{source}-poll.service"
    assert unit.exists(), f"missing {unit}"
    text = unit.read_text()
    assert "Type=oneshot" in text
    assert "User=observatory" in text
    assert "Group=observatory" in text
    assert "EnvironmentFile=/etc/observatory/observatory.env" in text
    assert f"ExecStart=/opt/observatory/.venv/bin/python -m observatory.pollers.{source}" in text
    assert f"SyslogIdentifier=obs-{source}-poll" in text
    assert "After=network-online.target chrony.service time-sync.target" in text
    # MUST NOT have Restart= on a oneshot — RESEARCH Anti-Pattern
    assert "Restart=" not in text, "oneshot unit must NOT have Restart= directive"


@pytest.mark.parametrize("source", SOURCES)
def test_timer_unit_exists(source: str) -> None:
    unit = DEPLOY / f"obs-{source}-poll.timer"
    assert unit.exists(), f"missing {unit}"
    text = unit.read_text()
    assert f"Requires=obs-{source}-poll.service" in text
    assert f"OnUnitActiveSec={INTERVALS[source]}" in text
    assert "RandomizedDelaySec=30" in text, "POLL-08 requires RandomizedDelaySec=30"
    assert "Persistent=true" in text, "missed firings after reboot must catch up"
    assert "WantedBy=timers.target" in text


def test_bootstrap_installs_all_three_timers() -> None:
    """bootstrap-pi.sh must enable all 3 timers in Section 14b."""
    script = (Path(__file__).resolve().parents[2] / "scripts" / "bootstrap-pi.sh").read_text()
    assert "SECTION 14b" in script
    for source in SOURCES:
        assert f"systemctl enable obs-{source}-poll.timer" in script
        assert f"obs-{source}-poll.service" in script
