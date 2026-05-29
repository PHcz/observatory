"""Daily soak-window evidence capture. Writes /api/health JSON + journalctl tail.

Output: ``/var/lib/observatory/soak/YYYY-MM-DD.json`` (override via
``OBSERVATORY_SOAK_DIR``; health URL override via ``OBSERVATORY_HEALTH_URL``).

Active only during the QA-06 soak window — the systemd timer is enabled at
T=0 by Plan 08-14 and disabled at T+7d. Always exits 0: capturing a partial
failure (e.g. /api/health unreachable) IS the evidence the operator needs.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
from pathlib import Path

import httpx

SOAK_DIR = Path(os.environ.get("OBSERVATORY_SOAK_DIR", "/var/lib/observatory/soak"))
HEALTH_URL = os.environ.get("OBSERVATORY_HEALTH_URL", "http://127.0.0.1:8000/api/health")
SERVICES = [
    "obs-api",
    "obs-muon",
    "obs-usgs-poll",
    "obs-emsc-poll",
    "obs-bgs-poll",
    "obs-noaa-poll",
    "obs-aurora-poll",
    "obs-blitzortung",
    "mosquitto",
]


def capture_health() -> tuple[dict[str, object] | None, str | None]:
    """Fetch /api/health. Returns (payload, None) on success or (None, error) on failure."""
    try:
        r = httpx.get(HEALTH_URL, timeout=5.0)
        r.raise_for_status()
        return r.json(), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def capture_journal(service: str) -> list[str]:
    """Tail the last 100 lines of journalctl for ``service`` over the past 24h."""
    try:
        proc = subprocess.run(
            ["/usr/bin/journalctl", "-u", service, "--since", "24h ago", "--no-pager"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        return proc.stdout.splitlines()[-100:]
    except Exception as exc:
        return [f"<journal capture failed: {type(exc).__name__}: {exc}>"]


def main() -> int:
    SOAK_DIR.mkdir(parents=True, exist_ok=True)
    today = dt.date.today().isoformat()
    out_path = SOAK_DIR / f"{today}.json"

    health, health_err = capture_health()
    journals = {svc: capture_journal(svc) for svc in SERVICES}

    snapshot = {
        "captured_at": dt.datetime.now(dt.UTC).isoformat(),
        "health": health,
        "health_error": health_err,
        "journals": journals,
    }
    out_path.write_text(json.dumps(snapshot, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
