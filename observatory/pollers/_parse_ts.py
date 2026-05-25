"""Strict ISO 8601 -> UTC unix epoch normalizer (POLL-07).

This handles ISO 8601 strings only. Sources emitting numeric epochs
(e.g. USGS GeoJSON `time` is int ms) MUST convert in their own parser.
Sources emitting naive datetimes (e.g. BGS RSS `pubDate`) MUST handle
the TZ assignment in their own parser BEFORE calling parse_ts (or skip
it entirely and convert manually).
"""

from __future__ import annotations

from datetime import UTC, datetime


class ParseError(ValueError):
    """Raised on naive datetime or unparseable input."""


def parse_ts(raw: str) -> int:
    """ISO 8601 -> UTC unix epoch (int seconds). Naive datetimes raise ParseError."""
    if not isinstance(raw, str) or not raw:
        raise ParseError(f"empty or non-string: {raw!r}")
    s = raw.strip()
    # fromisoformat in 3.11+ accepts Z natively, but normalize for safety.
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError as exc:
        raise ParseError(f"not ISO 8601: {raw!r}") from exc
    if dt.tzinfo is None:
        raise ParseError(f"naive datetime not accepted: {raw!r}")
    return int(dt.astimezone(UTC).timestamp())
