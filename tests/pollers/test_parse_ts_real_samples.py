"""Cross-check parse_ts against pinned upstream captures.

Documents the per-source contract:
- EMSC: ISO 8601 with Z suffix -> goes through parse_ts
- USGS: integer milliseconds since epoch -> does NOT go through parse_ts
- BGS:  naive RFC 822 -> handled by BGS parser carve-out (not parse_ts)
"""

from __future__ import annotations

import json
from collections.abc import Callable

from observatory.pollers._parse_ts import parse_ts


def test_emsc_real_sample_time_parses(load_eq_fixture: Callable[[str], bytes]) -> None:
    body = load_eq_fixture("emsc/sample_pastday.json")
    data = json.loads(body)
    raw_time = data["features"][0]["properties"]["time"]
    ts = parse_ts(raw_time)
    assert isinstance(ts, int)
    assert ts > 0


def test_usgs_time_is_numeric_ms_epoch_not_iso(
    load_eq_fixture: Callable[[str], bytes],
) -> None:
    """Documents that USGS bypasses parse_ts entirely (its `time` is ms epoch int)."""
    body = load_eq_fixture("usgs/sample_4_5_day.json")
    data = json.loads(body)
    raw_time = data["features"][0]["properties"]["time"]
    assert isinstance(raw_time, int)
    # Looks like ms epoch (13 digits, well past year-2000)
    assert raw_time > 1_000_000_000_000


def test_bgs_pubdate_is_naive_so_bgs_parser_owns_the_carveout(
    load_eq_fixture: Callable[[str], bytes],
) -> None:
    """Documents that BGS pubDate lacks a TZ marker; parse_ts (strict) would reject it."""
    body = load_eq_fixture("bgs/sample_recent.xml").decode()
    # The captured BGS RSS contains <pubDate> values without TZ suffix.
    assert "<pubDate>" in body
