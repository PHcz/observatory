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
    """Human-readable Telegram body for advisories against installed packages.

    One line per package: a single advisory keeps its id, several are counted
    (one line per advisory overflowed Telegram's 4096-character limit).
    """
    by_pkg: dict[tuple[str, str], list[InstalledVuln]] = {}
    for v in vulns:
        by_pkg.setdefault((v.package, v.version), []).append(v)
    lines = [f"⚠️ {len(by_pkg)} vulnerable package(s) INSTALLED on the Pi:"]
    for (pkg, version), group in sorted(by_pkg.items()):
        fixes = sorted({f for v in group for f in v.fix_versions}, key=_version_key)
        fix = f" (fix: {fixes[-1]})" if fixes else " (no fix yet)"
        if len(group) == 1:
            lines.append(f"• {pkg} {version}: {group[0].vuln_id}{fix}")
        else:
            lines.append(f"• {pkg} {version}: {len(group)} advisories{fix}")
    return "\n".join(lines)


def _version_key(version: str) -> tuple[tuple[int, str], ...]:
    """Sort key for version strings: numeric parts numerically, the rest as text."""
    return tuple(
        (int(part), "") if part.isdigit() else (-1, part)
        for part in version.replace("-", ".").split(".")
    )


async def fetch_open_alerts(
    token: str, repo: str, *, _transport: httpx.AsyncBaseTransport | None = None
) -> list[dict[str, Any]]:
    """Return every OPEN Dependabot alert for ``owner/repo``.

    Follows the ``Link: rel="next"`` pages: GitHub returns at most 100 alerts
    per page, and anything past the first page used to be dropped silently.
    Raises httpx.HTTPError on network failure or a non-2xx response.
    """
    url: str | None = f"{GITHUB_API}/repos/{repo}/dependabot/alerts"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    params: dict[str, str] | None = {"state": "open", "per_page": "100"}
    alerts: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=15.0, transport=_transport) as client:
        for _ in range(50):  # hard stop: 5000 alerts
            if url is None:
                break
            resp = await client.get(url, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                alerts.extend(data)
            url = resp.links.get("next", {}).get("url")
            params = None  # the "next" URL already carries the query
    return alerts


def summarise(alerts: list[dict[str, Any]], repo: str) -> str:
    """Human-readable Telegram body: one line per package, worst first.

    A package with one alert keeps the advisory summary and id; several are
    counted with the highest patched version. One line per ALERT made a
    9,003-character message for 71 alerts, which Telegram refused (> 4096).
    """
    by_pkg: dict[str, list[dict[str, Any]]] = {}
    for a in alerts:
        pkg = (a.get("dependency", {}) or {}).get("package", {}).get("name", "?")
        # PyPI names are case-insensitive; GitHub reports both "pillow" and "Pillow".
        key = next((k for k in by_pkg if k.lower() == pkg.lower()), pkg)
        by_pkg.setdefault(key, []).append(a)

    def severity(a: dict[str, Any]) -> str:
        return str((a.get("security_advisory", {}) or {}).get("severity", "?")).lower()

    def worst(group: list[dict[str, Any]]) -> str:
        return min((severity(a) for a in group), key=lambda s: _SEVERITY_ORDER.get(s, 99))

    def patched(a: dict[str, Any]) -> str | None:
        vuln = a.get("security_vulnerability") or {}
        first = vuln.get("first_patched_version") or {}
        ident = first.get("identifier")
        return str(ident) if ident else None

    lines = [f"⚠️ {len(alerts)} open Dependabot alert(s) in {len(by_pkg)} package(s) on {repo}:"]
    ordered = sorted(
        by_pkg.items(), key=lambda kv: (_SEVERITY_ORDER.get(worst(kv[1]), 99), kv[0].lower())
    )
    for pkg, group in ordered:
        sev = worst(group).upper()
        if len(group) == 1:
            adv = group[0].get("security_advisory", {}) or {}
            ghsa = adv.get("ghsa_id", "")
            suffix = f" ({ghsa})" if ghsa else ""
            lines.append(f"• [{sev}] {pkg}: {adv.get('summary', '')}{suffix}")
            continue
        fixes = sorted({f for a in group if (f := patched(a))}, key=_version_key)
        fix = f" (fix: >= {fixes[-1]})" if fixes else " (no fix yet)"
        lines.append(f"• [{sev}] {pkg}: {len(group)} alerts{fix}")
    return "\n".join(lines)


async def _amain() -> int:
    token = settings.vuln_check_github_token.get_secret_value()
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
