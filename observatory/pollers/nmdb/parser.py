"""NMDB / NEST ASCII parser (Phase 13, MU2-06).

Parses a NEST ``output=ascii`` export of neutron-monitor counts into a list of
``NmdbCount`` rows + a freshness/meta dict. The strategy mirrors the airquality
parser: STRICT on structure (no data rows at all -> ``ValueError`` so the oneshot
``__main__`` can write a ``parse_fail`` audit row) and per-row TOLERANT (a
``null``/``None`` count token becomes ``counts_per_sec=None`` and is counted
toward the parse-failure threshold via ``meta["failures"]``).

NEST wraps the data in an HTML page; the rows of interest match
``YYYY-MM-DD HH:MM:SS;<float|null>`` (NEST uses ``;`` separators in the ASCII
export). Lines that do not match are skipped. Timestamps are UTC at the BEGIN of
the interval (NMDB convention) and parsed directly to a UTC epoch — NOT via the
naive-local ``utc_offset_seconds`` carve-out used by forecast/air_quality.

``counts_per_sec`` is the ABSOLUTE counts/s from a ``yunits=0`` export (Pitfall 3):
omitting ``yunits=0`` would yield a relative scale that silently breaks the
%-of-baseline math, so the parser asserts nothing about scale but the poller URL
pins ``yunits=0``.
"""

from __future__ import annotations

import re
import time
from datetime import UTC, datetime

from observatory.pollers._types import NmdbCount

# Hyphen-minus only (ruff RUF001/RUF003 — no en-dash in any string).
_NULL_TOKENS = frozenset({"null", "none", "nan"})
_ROW = re.compile(
    r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})\s*;\s*([\d.+eE-]+|null|None|NaN)?\s*$"
)


def parse_nmdb(body: bytes, station: str) -> tuple[list[NmdbCount], dict[str, int | str]]:
    """Parse a NEST ASCII export into NMDB counts + a meta dict.

    Returns ``(rows, meta)`` where ``meta`` carries ``fetched_at`` (int),
    ``station`` (str) and ``failures`` (int — gap/null rows counted for the
    ``compute_parse_outcome`` threshold). Raises ``ValueError`` if the body
    contains no recognisable data rows (structural failure).
    """
    text = body.decode("utf-8", "replace")
    rows: list[NmdbCount] = []
    failures = 0
    for raw_line in text.splitlines():
        line = raw_line.strip()
        m = _ROW.match(line)
        if m is None:
            continue
        date_part, time_part, val = m.groups()
        ts = int(datetime.fromisoformat(f"{date_part}T{time_part}").replace(tzinfo=UTC).timestamp())
        if val is None or val.lower() in _NULL_TOKENS:
            failures += 1
            cps: float | None = None
        else:
            try:
                cps = float(val)
            except ValueError:
                failures += 1
                cps = None
        rows.append(NmdbCount(ts=ts, station=station, counts_per_sec=cps))

    if not rows:
        raise ValueError("no NMDB data rows found in NEST ascii export")

    meta: dict[str, int | str] = {
        "fetched_at": int(time.time()),
        "station": station,
        "failures": failures,
    }
    return rows, meta
