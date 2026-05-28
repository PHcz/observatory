"""Daily soak-window evidence capture. Writes /api/health JSON + journalctl tail.

Output: ``/var/lib/observatory/soak/YYYY-MM-DD.json``

Mirrors ``scripts/backup.py`` shape (structlog + sd-friendly main). Active
only during the QA-06 soak window — the systemd timer is enabled at T=0 and
disabled at T+7d.
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
from pathlib import Path

import httpx

SOAK_DIR = Path("/var/lib/observatory/soak")
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


def main() -> int:
    SOAK_DIR.mkdir(parents=True, exist_ok=True)
    today = dt.date.today().isoformat()
    out_path = SOAK_DIR / f"{today}.json"

    health = httpx.get("http://127.0.0.1:8000/api/health", timeout=5.0).json()
    journals = {
        svc: subprocess.run(
            ["/usr/bin/journalctl", "-u", svc, "--since", "24h ago", "--no-pager"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.splitlines()[-100:]
        for svc in SERVICES
    }
    snapshot = {
        "captured_at": dt.datetime.now(dt.UTC).isoformat(),
        "health": health,
        "journals": journals,
    }
    out_path.write_text(json.dumps(snapshot, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
