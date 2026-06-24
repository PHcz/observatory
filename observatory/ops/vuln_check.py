"""Daily Dependabot vulnerability check → Telegram.

Polls the GitHub Dependabot alerts API for OPEN alerts on the configured repo
and, if any exist, sends a one-shot Telegram message summarising them. Runs on
the Pi via obs-vuln-check.timer (daily). Outbound-only — same sanctioned-egress
justification as the external pollers and ntfy/Telegram alerts: no inbound
exposure, no tunnel into the LAN.

Exit codes (for the systemd unit / journal):
    0  clean run — no open alerts, or nothing to do (no token / Telegram off)
    1  the GitHub fetch failed (network / auth / rate-limit)

Config (Pi .env only — never commit real values):
    vuln_check_github_token  — fine-grained PAT, "Dependabot alerts: read"
    vuln_check_repo          — "owner/repo" (default PHcz/observatory)
    alert_telegram_*         — reused for delivery (must be enabled + configured)
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

import httpx
import structlog

from observatory.config import settings
from observatory.weather.alerts.notifier import notify_telegram

log = structlog.get_logger(__name__)

GITHUB_API = "https://api.github.com"
_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


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

    if not token:
        log.warning("vuln_check.no_token")
        return 0  # not configured yet — a no-op, not a failure

    try:
        alerts = await fetch_open_alerts(token, repo)
    except Exception as exc:
        log.error("vuln_check.fetch_failed", error=str(exc))
        return 1

    if not alerts:
        log.info("vuln_check.clean", repo=repo)
        return 0

    log.info("vuln_check.alerts_found", repo=repo, count=len(alerts))
    await notify_telegram(title="Dependabot Alerts", message=summarise(alerts, repo))
    return 0


def main() -> int:
    return asyncio.run(_amain())


if __name__ == "__main__":
    sys.exit(main())
