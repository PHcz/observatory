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


# ---------------------------------------------------------------------------
# On-device audit (security audit 2026-10-20, M10)
# ---------------------------------------------------------------------------
# Dependabot, the pre-push pip-audit and this daily check all inspected uv.lock
# and reported "clean" while the Pi ran fastapi 0.136 / starlette 1.3 / uvicorn
# 0.39 with 15 on-device advisories. The daily check must also audit what is
# actually INSTALLED where it runs.

import asyncio  # noqa: E402
import json  # noqa: E402
import sysconfig  # noqa: E402

import pytest  # noqa: E402
from pydantic import SecretStr  # noqa: E402

from observatory.ops import vuln_check  # noqa: E402

_PIP_AUDIT_JSON = json.dumps(
    {
        "dependencies": [
            {
                "name": "starlette",
                "version": "1.3.1",
                "vulns": [
                    {
                        "id": "PYSEC-2026-161",
                        "fix_versions": ["1.8.0"],
                        "aliases": [],
                        "description": "x",
                    }
                ],
            },
            {"name": "httpx", "version": "0.28.1", "vulns": []},
            {"name": "observatory", "skip_reason": "Dependency not found on PyPI"},
        ],
        "fixes": [],
    }
)


def test_parse_pip_audit_reports_only_vulnerable_packages() -> None:
    found = vuln_check.parse_pip_audit(_PIP_AUDIT_JSON)
    assert [(v.package, v.version, v.vuln_id) for v in found] == [
        ("starlette", "1.3.1", "PYSEC-2026-161")
    ]
    assert found[0].fix_versions == ("1.8.0",)


def test_summarise_installed_names_package_version_and_fix() -> None:
    out = vuln_check.summarise_installed(vuln_check.parse_pip_audit(_PIP_AUDIT_JSON))
    assert "INSTALLED on the Pi" in out
    assert "starlette 1.3.1" in out and "PYSEC-2026-161" in out and "1.8.0" in out


def test_audits_the_running_interpreters_own_site_packages() -> None:
    """The unit runs under the app venv's python, so its purelib IS the venv."""
    assert vuln_check.installed_site_packages() == sysconfig.get_paths()["purelib"]


def test_alerts_when_dependabot_is_clean_but_the_pi_is_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The exact failure the audit found: lockfile clean, installed packages not."""
    sent: list[tuple[str, str]] = []

    async def no_alerts(token: str, repo: str) -> list[dict[str, object]]:
        return []

    async def capture(title: str, message: str) -> None:
        sent.append((title, message))

    monkeypatch.setattr(vuln_check, "fetch_open_alerts", no_alerts)
    monkeypatch.setattr(vuln_check, "run_pip_audit", lambda site: _PIP_AUDIT_JSON)
    monkeypatch.setattr(vuln_check, "notify_telegram", capture)
    monkeypatch.setattr(
        vuln_check,
        "settings",
        type("S", (), {"vuln_check_github_token": SecretStr("t"), "vuln_check_repo": "o/r"})(),
    )
    assert asyncio.run(vuln_check._amain()) == 0
    assert len(sent) == 1 and "starlette 1.3.1" in sent[0][1]


def test_on_device_audit_still_runs_without_a_github_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[str] = []

    async def capture(title: str, message: str) -> None:
        sent.append(message)

    monkeypatch.setattr(vuln_check, "run_pip_audit", lambda site: _PIP_AUDIT_JSON)
    monkeypatch.setattr(vuln_check, "notify_telegram", capture)
    monkeypatch.setattr(
        vuln_check,
        "settings",
        type("S", (), {"vuln_check_github_token": SecretStr(""), "vuln_check_repo": "o/r"})(),
    )
    asyncio.run(vuln_check._amain())
    assert sent and "starlette" in sent[0]


def test_clean_on_both_sides_sends_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[str] = []

    async def no_alerts(token: str, repo: str) -> list[dict[str, object]]:
        return []

    async def capture(title: str, message: str) -> None:
        sent.append(message)

    clean = json.dumps({"dependencies": [{"name": "httpx", "version": "1", "vulns": []}]})
    monkeypatch.setattr(vuln_check, "fetch_open_alerts", no_alerts)
    monkeypatch.setattr(vuln_check, "run_pip_audit", lambda site: clean)
    monkeypatch.setattr(vuln_check, "notify_telegram", capture)
    monkeypatch.setattr(
        vuln_check,
        "settings",
        type("S", (), {"vuln_check_github_token": SecretStr("t"), "vuln_check_repo": "o/r"})(),
    )
    assert asyncio.run(vuln_check._amain()) == 0
    assert sent == []
