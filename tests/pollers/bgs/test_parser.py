"""BGS RSS parser tests — closes POLL-03 parse contract + checker WARNING 1.

The parser is contractually defined to return ``(events, parse_failures)``:
good items flow through; per-item failures (missing link match, missing
Magnitude) are counted and WARNING-logged with a truncated raw dump;
structural failures (not-XML) still raise.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from structlog.testing import capture_logs

from observatory.pollers._types import EarthquakeEvent
from observatory.pollers.bgs.parser import parse_bgs

# ---------- Synthetic feed builder ----------


def _wrap(items_xml: str) -> bytes:
    return (
        b'<?xml version="1.0"?>\n'
        b'<rss version="2.0" xmlns:geo="http://www.w3.org/2003/01/geo/wgs84_pos#" '
        b'xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
        b"<channel>\n"
        b"<title>Recent earthquakes around the UK</title>\n"
        b"<link>http://earthquakes.bgs.ac.uk/</link>\n"
        b"<description>test</description>\n" + items_xml.encode() + b"</channel>\n</rss>\n"
    )


def _item(
    *,
    link: str = "http://earthquakes.bgs.ac.uk/earthquakes/recent_events/20260524200750.html",
    pub_date: str = "Sun, 24 May 2026 20:10:46",
    lat: str = "50.080",
    lon: str = "0.682",
    description: str = (
        "Origin date/time: Sun, 24 May 2026 20:10:46 ; Location: ENGLISH CHANNEL ; "
        "Lat/long: 50.080,0.682 ; Depth: 14 km ; Magnitude:  2.2"
    ),
    title: str = "UK Earthquake alert : M  2.2 :ENGLISH CHANNEL",
) -> str:
    return (
        "<item>\n"
        f"<title>{title}</title>\n"
        f"<description>{description}</description>\n"
        f"<link>{link}</link>\n"
        f"<pubDate>{pub_date}</pubDate>\n"
        "<category>EQUK</category>\n"
        f"<geo:lat>{lat}</geo:lat>\n"
        f"<geo:long>{lon}</geo:long>\n"
        "</item>\n"
    )


# ---------- Real fixture ----------


def test_parse_real_fixture(load_eq_fixture: Callable[[str], bytes]) -> None:
    body = load_eq_fixture("bgs/sample_recent.xml")
    events, failures = parse_bgs(body)
    assert len(events) >= 1
    # Real-world fixture is allowed some failures (missing magnitude, etc.) but
    # the ratio MUST stay under 0.5 — otherwise BGS feed shape is broken.
    total = len(events) + failures
    assert failures / total <= 0.5, (
        f"BGS fixture failure ratio {failures}/{total} exceeds 0.5 — feed shape changed"
    )
    for ev in events:
        assert isinstance(ev, EarthquakeEvent)
        assert ev.source == "bgs"
        assert isinstance(ev.external_id, str) and ev.external_id
        # external_id is the 14-digit link slug
        assert len(ev.external_id) == 14 and ev.external_id.isdigit()
        assert isinstance(ev.ts, int) and ev.ts > 0
        assert isinstance(ev.magnitude, float)
        assert -90.0 <= ev.latitude <= 90.0
        assert -180.0 <= ev.longitude <= 180.0
        assert ev.depth_km is None or isinstance(ev.depth_km, float)


def test_parse_returns_unique_external_ids_on_real_fixture(
    load_eq_fixture: Callable[[str], bytes],
) -> None:
    body = load_eq_fixture("bgs/sample_recent.xml")
    events, _ = parse_bgs(body)
    ids = [ev.external_id for ev in events]
    assert len(set(ids)) == len(ids)


def test_parse_real_fixture_ts_in_2026_range(
    load_eq_fixture: Callable[[str], bytes],
) -> None:
    body = load_eq_fixture("bgs/sample_recent.xml")
    events, _ = parse_bgs(body)
    lo = 1767225600  # 2026-01-01
    hi = 1798761600  # 2027-01-01
    for ev in events:
        assert lo <= ev.ts <= hi, f"ts {ev.ts} for {ev.external_id} not in 2026"


# ---------- Field-by-field synthetic checks ----------


def test_parse_external_id_from_link_regex() -> None:
    body = _wrap(
        _item(link="http://earthquakes.bgs.ac.uk/earthquakes/recent_events/20260524200750.html")
    )
    events, failures = parse_bgs(body)
    assert failures == 0
    assert events[0].external_id == "20260524200750"


def test_parse_skips_items_without_matching_link() -> None:
    body = _wrap(_item(link="http://example.com/other/path.html"))
    events, failures = parse_bgs(body)
    assert events == []
    assert failures == 1


def test_parse_naive_pubdate_assumed_utc() -> None:
    body = _wrap(_item(pub_date="Sun, 24 May 2026 20:10:46"))
    events, _ = parse_bgs(body)
    expected = int(datetime(2026, 5, 24, 20, 10, 46, tzinfo=UTC).timestamp())
    assert events[0].ts == expected


def test_parse_aware_pubdate_respected() -> None:
    # +0100 (BST) -> one hour earlier in UTC epoch
    body = _wrap(_item(pub_date="Sun, 24 May 2026 20:10:46 +0100"))
    events, _ = parse_bgs(body)
    expected = int(datetime(2026, 5, 24, 19, 10, 46, tzinfo=UTC).timestamp())
    assert events[0].ts == expected


def test_parse_geo_namespace() -> None:
    body = _wrap(_item(lat="50.080", lon="0.682"))
    events, _ = parse_bgs(body)
    assert events[0].latitude == 50.080
    assert events[0].longitude == 0.682


def test_parse_extracts_magnitude_from_description() -> None:
    body = _wrap(
        _item(
            description=(
                "Origin date/time: Sun, 24 May 2026 20:10:46 ; "
                "Location: PLACE ; Lat/long: 0,0 ; Depth: 5 km ; Magnitude:  2.2"
            )
        )
    )
    events, _ = parse_bgs(body)
    assert events[0].magnitude == 2.2


def test_parse_extracts_depth_from_description() -> None:
    body = _wrap(
        _item(
            description=(
                "Origin date/time: x ; Location: PLACE ; Lat/long: 0,0 ; "
                "Depth: 14 km ; Magnitude: 2.2"
            )
        )
    )
    events, _ = parse_bgs(body)
    assert events[0].depth_km == 14.0


def test_parse_handles_missing_depth() -> None:
    body = _wrap(
        _item(
            description=("Origin date/time: x ; Location: PLACE ; Lat/long: 0,0 ; Magnitude: 2.2")
        )
    )
    events, failures = parse_bgs(body)
    assert failures == 0
    assert events[0].depth_km is None


def test_parse_extracts_location_from_description() -> None:
    body = _wrap(
        _item(
            description=(
                "Origin date/time: x ; Location: ENGLISH CHANNEL ; "
                "Lat/long: 0,0 ; Depth: 5 km ; Magnitude: 2.2"
            )
        )
    )
    events, _ = parse_bgs(body)
    assert events[0].place == "ENGLISH CHANNEL"


def test_parse_skips_items_without_magnitude() -> None:
    body = _wrap(
        _item(description=("Origin date/time: x ; Location: PLACE ; Lat/long: 0,0 ; Depth: 5 km"))
    )
    events, failures = parse_bgs(body)
    assert events == []
    assert failures == 1


def test_parse_empty_channel() -> None:
    body = _wrap("")
    events, failures = parse_bgs(body)
    assert events == []
    assert failures == 0


# ---------- Partial-parse cases (closes checker WARNING 1) ----------


def test_parse_partial_failure_increments_counter() -> None:
    good_items = "".join(
        _item(link=f"http://earthquakes.bgs.ac.uk/earthquakes/recent_events/2026052420{i:04d}.html")
        for i in range(8)
    )
    bad_items = _item(link="http://example.com/no/match.html") + _item(
        description="no magnitude here ; Location: X ; Lat/long: 0,0"
    )
    body = _wrap(good_items + bad_items)
    events, failures = parse_bgs(body)
    assert len(events) == 8
    assert failures == 2


def test_parse_partial_failure_logs_warning_with_truncated_raw() -> None:
    bad_items = _item(link="http://example.com/no/match.html") + _item(
        description="no magnitude here ; Location: X ; Lat/long: 0,0"
    )
    body = _wrap(bad_items)
    with capture_logs() as logs:
        events, failures = parse_bgs(body)
    assert events == []
    assert failures == 2
    warnings = [e for e in logs if e.get("log_level") == "warning"]
    assert len(warnings) == 2
    for entry in warnings:
        assert "raw" in entry
        assert isinstance(entry["raw"], str)
        assert len(entry["raw"]) <= 200


# ---------- Structural failures still raise ----------


def test_parse_not_xml_raises() -> None:
    import xml.etree.ElementTree as ET

    with pytest.raises(ET.ParseError):
        parse_bgs(b"<not-xml")


# ---------- Smoke: parser does NOT delegate naive ts handling to parse_ts ----------


def test_parser_source_does_not_import_parse_ts() -> None:
    """BGS parser handles naive pubDate itself; must not route through strict parse_ts."""
    from pathlib import Path

    src = Path("observatory/pollers/bgs/parser.py").read_text()
    assert "parse_ts" not in src, (
        "BGS parser must NOT import parse_ts — it owns the naive-UTC carve-out"
    )
