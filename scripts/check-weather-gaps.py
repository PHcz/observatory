#!/usr/bin/env python3
"""Gap-check the weather table for Phase 3 success criterion #4 (48h soak).

Queries the weather table over a configurable window and reports the maximum
consecutive-row gap. Drives the operator-facing acceptance bit for the deferred
48-hour soak test (success criterion #4 in .planning/ROADMAP.md §Phase 3).

Exit codes:
    0 — max gap <= threshold (default 4500s = 75min = 3x 25min upload interval)
    1 — max gap > threshold OR no rows in window
    2 — bad arguments / DB error

Examples:
    python scripts/check-weather-gaps.py                            # last 48h, threshold 4500s
    python scripts/check-weather-gaps.py --since-hours 24           # last 24h
    python scripts/check-weather-gaps.py --threshold-sec 6000       # tolerate up to 100min
    python scripts/check-weather-gaps.py --db-path data/test.db
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from typing import Any

from observatory.db.connection import get_conn


def analyze_gaps(db_path: str | None, since_ts: int, threshold_sec: int) -> dict[str, Any]:
    """Return summary dict: row_count, max_gap_sec, mean_gap_sec, pass."""
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT ts FROM weather WHERE ts >= ? ORDER BY ts",
            (since_ts,),
        ).fetchall()
    timestamps = [int(r["ts"]) for r in rows]
    if len(timestamps) < 2:
        return {
            "row_count": len(timestamps),
            "max_gap_sec": None,
            "mean_gap_sec": None,
            "threshold_sec": threshold_sec,
            "pass": False,
            "reason": "insufficient rows (<2) in window",
        }
    gaps = [timestamps[i] - timestamps[i - 1] for i in range(1, len(timestamps))]
    max_gap = max(gaps)
    mean_gap = sum(gaps) / len(gaps)
    return {
        "row_count": len(timestamps),
        "max_gap_sec": max_gap,
        "mean_gap_sec": round(mean_gap, 1),
        "threshold_sec": threshold_sec,
        "pass": max_gap <= threshold_sec,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Phase 3 weather-gap audit (success criterion #4)")
    p.add_argument("--since-hours", type=float, default=48.0)
    p.add_argument(
        "--threshold-sec",
        type=int,
        default=4500,
        help="max permitted gap (default 4500s = 3x 25min upload)",
    )
    p.add_argument("--db-path", default=None)
    args = p.parse_args()

    if args.since_hours <= 0:
        print("error: --since-hours must be > 0", file=sys.stderr)
        return 2

    since_ts = int(time.time()) - int(args.since_hours * 3600)
    try:
        result = analyze_gaps(args.db_path, since_ts, args.threshold_sec)
    except sqlite3.Error as exc:
        print(f"error: db read failed: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, indent=2))
    summary = (
        f"weather-gaps: rows={result['row_count']} "
        f"max_gap={result['max_gap_sec']}s "
        f"mean_gap={result['mean_gap_sec']}s "
        f"threshold={result['threshold_sec']}s "
        f"{'PASS' if result['pass'] else 'FAIL'}"
    )
    print(summary, file=sys.stderr)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
