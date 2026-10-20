"""Daily vulnerability check → Telegram: Dependabot alerts AND installed packages.

1. Polls the GitHub Dependabot alerts API for OPEN alerts on the configured repo.
2. Audits the packages actually INSTALLED where it runs, with pip-audit.

(2) exists because (1) only ever sees uv.lock. Until 2026-10-20 the Pi ran
fastapi 0.136 / starlette 1.3 / uvicorn 0.39 with 15 on-device advisories while
Dependabot, the pre-push pip-audit and this check all reported "clean"
(security audit M10). If either side finds something, one Telegram message
summarises both. Runs on
the Pi via obs-vuln-check.timer (daily). Outbound-only — same sanctioned-egress
justification as the external pollers and ntfy/Telegram alerts: no inbound
exposure, no tunnel into the LAN.

Exit codes (for the systemd unit / journal):
    0  clean run -- nothing found, or findings reported
    1  the GitHub fetch or the on-device pip-audit failed

Config (Pi .env only — never commit real values):
    vuln_check_github_token  — fine-grained PAT, "Dependabot alerts: read"
                               (optional: without it only the on-device audit runs)
    vuln_check_repo          — "owner/repo" (default PHcz/observatory)
    alert_telegram_*         — reused for delivery (must be enabled + configured)
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
import sysconfig
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from observatory.config import settings
from observatory.logging import configure_logging
from observatory.weather.alerts.notifier import notify_telegram

log = structlog.get_logger(__name__)

GITHUB_API = "https://api.github.com"
_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

# Pinned so the daily job always runs the same auditor. It runs as an isolated
# `uv tool`, never inside the app venv -- that is runtime-only since M10.
PIP_AUDIT_SPEC = "pip-audit==2.10.1"


@dataclass(frozen=True)
class InstalledVuln:
    """One advisory against one package installed in the running environment."""

    package: str
    version: str
    vuln_id: str
    fix_versions: tuple[str, ...]


def installed_site_packages() -> str:
    """site-packages of the running interpreter.

    obs-vuln-check runs under /opt/observatory/.venv/bin/python, so this is the
    exact environment every observatory service runs from -- no path to drift.
    """
    return sysconfig.get_paths()["purelib"]


def run_pip_audit(site_packages: str) -> str:
    """Run pip-audit against an installed environment; return its JSON output."""
    uv = shutil.which("uv") or "/usr/local/bin/uv"
    proc = subprocess.run(
        [
            uv,
            "tool",
            "run",
            "--from",
            PIP_AUDIT_SPEC,
            "pip-audit",
            "--path",
            site_packages,
            "--format",
            "json",
            "--progress-spinner",
            "off",
        ],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    # pip-audit exits 1 when it FINDS vulnerabilities; anything else is a failure.
    if proc.returncode not in (0, 1):
        raise RuntimeError(f"pip-audit exited {proc.returncode}: {proc.stderr.strip()[-300:]}")
    return proc.stdout


def parse_pip_audit(text: str) -> list[InstalledVuln]:
    """Vulnerable packages only; clean and skipped (not-on-PyPI) entries are dropped."""
    data = json.loads(text)
    found: list[InstalledVuln] = []
    for dep in data.get("dependencies", []):
        for vuln in dep.get("vulns") or []:
            found.append(
                InstalledVuln(
                    package=str(dep.get("name", "?")),
                    version=str(dep.get("version", "?")),
                    vuln_id=str(vuln.get("id", "?")),
                    fix_versions=tuple(str(v) for v in vuln.get("fix_versions") or ()),
                )
            )
    return found


def summarise_installed(vulns: list[InstalledVuln]) -> str:
    """Human-readable Telegram body for advisories against installed packages."""
    packages = {(v.package, v.version) for v in vulns}
    lines = [f"⚠️ {len(packages)} vulnerable package(s) INSTALLED on the Pi:"]
    for v in sorted(vulns, key=lambda v: (v.package, v.vuln_id)):
        fix = f" (fix: {', '.join(v.fix_versions)})" if v.fix_versions else " (no fix yet)"
        lines.append(f"• {v.package} {v.version}: {v.vuln_id}{fix}")
    return "\n".join(lines)


async def fetch_open_alerts(token: str, repo: str) -> list[dict[str, Any]]:
    """Return the list of OPEN Dependabot alerts for ``owner/repo``.

    Raises httpx.HTTPError on network failure or a non-2xx response.
    """
    url = f"{GITHUB_API}/repos/{repo}/dependabot/alerts"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    params = {"state": "open", "per_page": "100"}
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()
    return data if isinstance(data, list) else []


def summarise(alerts: list[dict[str, Any]], repo: str) -> str:
    """Human-readable Telegram body listing the open alerts, worst-first."""

    def sort_key(a: dict[str, Any]) -> int:
        sev = str(a.get("security_advisory", {}).get("severity", "")).lower()
        return _SEVERITY_ORDER.get(sev, 99)

    lines = [f"⚠️ {len(alerts)} open Dependabot alert(s) on {repo}:"]
    for a in sorted(alerts, key=sort_key):
        adv = a.get("security_advisory", {}) or {}
        sev = str(adv.get("severity", "?")).upper()
        ghsa = adv.get("ghsa_id", "")
        pkg = (a.get("dependency", {}) or {}).get("package", {}).get("name", "?")
        summary = adv.get("summary", "")
        suffix = f" ({ghsa})" if ghsa else ""
        lines.append(f"• [{sev}] {pkg}: {summary}{suffix}")
    return "\n".join(lines)


async def _amain() -> int:
    token = settings.vuln_check_github_token
    repo = settings.vuln_check_repo
    failed = False
    sections: list[str] = []

    alerts: list[dict[str, Any]] = []
    if token:
        try:
            alerts = await fetch_open_alerts(token, repo)
        except Exception as exc:
            log.error("vuln_check.fetch_failed", error=str(exc))
            failed = True
    else:
        log.warning("vuln_check.no_token")  # Dependabot side skipped; on-device still runs
    if alerts:
        log.info("vuln_check.alerts_found", repo=repo, count=len(alerts))
        sections.append(summarise(alerts, repo))

    installed: list[InstalledVuln] = []
    try:
        raw = await asyncio.to_thread(run_pip_audit, installed_site_packages())
        installed = parse_pip_audit(raw)
    except Exception as exc:
        log.error("vuln_check.pip_audit_failed", error=str(exc))
        failed = True
    if installed:
        log.info("vuln_check.installed_vulns_found", count=len(installed))
        sections.append(summarise_installed(installed))

    if not sections:
        log.info("vuln_check.clean", repo=repo)
    else:
        title = "Vulnerability Alerts" if installed else "Dependabot Alerts"
        await notify_telegram(title=title, message="\n\n".join(sections))
    return 1 if failed else 0


def main() -> int:
    configure_logging()
    return asyncio.run(_amain())


if __name__ == "__main__":
    sys.exit(main())
