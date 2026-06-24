"""Daily Dependabot vuln check — pure-function tests for summarise()."""

from __future__ import annotations

from typing import Any

from observatory.ops.vuln_check import summarise


def _alert(severity: str, pkg: str, summary: str, ghsa: str) -> dict[str, Any]:
    return {
        "security_advisory": {"severity": severity, "summary": summary, "ghsa_id": ghsa},
        "dependency": {"package": {"name": pkg}},
    }


def test_summarise_header_counts_alerts() -> None:
    alerts = [_alert("high", "starlette", "DoS", "GHSA-x")]
    out = summarise(alerts, "PHcz/observatory")
    assert "1 open Dependabot alert(s) on PHcz/observatory" in out
    assert "[HIGH] starlette: DoS (GHSA-x)" in out


def test_summarise_orders_worst_first() -> None:
    alerts = [
        _alert("low", "a", "low bug", "GHSA-low"),
        _alert("critical", "b", "crit bug", "GHSA-crit"),
        _alert("medium", "c", "med bug", "GHSA-med"),
    ]
    out = summarise(alerts, "r")
    lines = out.splitlines()[1:]  # drop header
    assert lines[0].startswith("• [CRITICAL]")
    assert lines[1].startswith("• [MEDIUM]")
    assert lines[2].startswith("• [LOW]")


def test_summarise_tolerates_missing_fields() -> None:
    # Malformed alert (no advisory/dependency) must not raise.
    out = summarise([{}], "r")
    assert "[?]" in out and "?:" in out
