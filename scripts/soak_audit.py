"""End-of-soak audit — walks ``/var/lib/observatory/soak/*.json`` over 7 days.

Produces a JSON summary on stdout. Operator interprets vs the data-quality
bar in ``08-CONTEXT.md`` §"7-day soak methodology" and pastes the result into
``08-SOAK.md`` at T+7d.

Summary fields:
  - ``snapshots_found``: count of parseable daily snapshot files
  - ``days_all_healthy``: count of snapshots whose ``health.status == 'healthy'``
  - ``pi_throttled_at_end``: latest snapshot's ``health.pi.throttled`` (None if
    health absent / pi block missing)
  - ``files``: list of snapshot file paths walked (sorted, ascending)

Override snapshot directory via ``OBSERVATORY_SOAK_DIR``.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, cast

SOAK_DIR = Path(os.environ.get("OBSERVATORY_SOAK_DIR", "/var/lib/observatory/soak"))


def main() -> int:
    files = sorted(SOAK_DIR.glob("*.json"))
    snaps: list[dict[str, Any]] = []
    for f in files:
        try:
            snaps.append(cast("dict[str, Any]", json.loads(f.read_text())))
        except (json.JSONDecodeError, OSError):
            # Corrupt or unreadable snapshot — skip, don't crash the audit.
            continue

    days_all_healthy = sum(1 for s in snaps if (s.get("health") or {}).get("status") == "healthy")
    pi_throttled_at_end: str | None = None
    if snaps:
        last_health = snaps[-1].get("health") or {}
        pi_block = last_health.get("pi") or {}
        pi_throttled_at_end = pi_block.get("throttled")

    summary = {
        "snapshots_found": len(snaps),
        "days_all_healthy": days_all_healthy,
        "pi_throttled_at_end": pi_throttled_at_end,
        "files": [str(f) for f in files],
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
