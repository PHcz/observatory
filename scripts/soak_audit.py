"""End-of-soak audit — walks ``/var/lib/observatory/soak/*.json`` over 7 days.

Skeleton only — implemented in detail by Plan 08-16.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SOAK_DIR = Path("/var/lib/observatory/soak")


def main() -> int:
    files = sorted(SOAK_DIR.glob("*.json"))
    print(json.dumps({"snapshots_found": len(files), "files": [str(f) for f in files]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
