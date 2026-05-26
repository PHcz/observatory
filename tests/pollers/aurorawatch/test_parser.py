"""AuroraWatch UK parser tests (TDD RED).

Tests cover:
- Compact `+0000` tz form (Python 3.11 fromisoformat rejects it; parser carves
  out via email.utils.parsedate_to_datetime)
- Strict ISO `+00:00` form (fromisoformat handles directly)
- `Z` suffix form
- All 4 status values (green/yellow/amber/red)
- detail column = colon-joined project_id:site_id
- detail=None when both project_id and site_id empty
- ValueError on: empty datetime, missing site_status, unknown status_id,
  malformed XML
- Pinned fixture round-trip
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from observatory.pollers.aurorawatch.parser import parse_aurora


def _xml(
    *,
    dt: str = "2026-05-25T22:48:32+0000",
    project_id: str = "project:SAMNET",
    site_id: str = "site:SAMNET:CRK2",
    status_id: str = "green",
    include_site: bool = True,
) -> bytes:
    site = (
        f'<site_status project_id="{project_id}" site_id="{site_id}" status_id="{status_id}"/>'
        if include_site
        else ""
    )
    return (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<current_status api_version="0.2.5">'
        f"<updated><datetime>{dt}</datetime></updated>"
        f"{site}"
        f"</current_status>"
    ).encode()


# ---------- Datetime carve-out ----------


def test_parse_compact_tz_assumed_utc() -> None:
    body = _xml(dt="2026-05-25T22:48:32+0000")
    ts, status, detail = parse_aurora(body)
    expected = int(datetime(2026, 5, 25, 22, 48, 32, tzinfo=UTC).timestamp())
    assert ts == expected
    assert status == "green"
    assert detail == "project:SAMNET:site:SAMNET:CRK2"


def test_parse_strict_iso_with_colon() -> None:
    body = _xml(dt="2026-05-25T22:48:32+00:00")
    ts, _, _ = parse_aurora(body)
    expected = int(datetime(2026, 5, 25, 22, 48, 32, tzinfo=UTC).timestamp())
    assert ts == expected


def test_parse_z_suffix() -> None:
    body = _xml(dt="2026-05-25T22:48:32Z")
    ts, _, _ = parse_aurora(body)
    expected = int(datetime(2026, 5, 25, 22, 48, 32, tzinfo=UTC).timestamp())
    assert ts == expected


# ---------- All four status values ----------


@pytest.mark.parametrize("status_id", ["green", "yellow", "amber", "red"])
def test_parse_all_four_status_values(status_id: str) -> None:
    body = _xml(status_id=status_id)
    _, status, _ = parse_aurora(body)
    assert status == status_id


def test_parse_status_id_lowercased() -> None:
    body = _xml(status_id="GREEN")
    _, status, _ = parse_aurora(body)
    assert status == "green"


# ---------- detail column shape ----------


def test_parse_detail_colon_joined() -> None:
    body = _xml(project_id="p", site_id="s")
    _, _, detail = parse_aurora(body)
    assert detail == "p:s"


def test_parse_detail_none_when_both_empty() -> None:
    body = _xml(project_id="", site_id="")
    _, _, detail = parse_aurora(body)
    assert detail is None


# ---------- Error paths ----------


def test_parse_unknown_status_raises() -> None:
    body = _xml(status_id="blue")
    with pytest.raises(ValueError, match="invalid status_id"):
        parse_aurora(body)


def test_parse_missing_datetime_raises() -> None:
    body = (
        b'<?xml version="1.0"?>'
        b'<current_status api_version="0.2.5">'
        b"<updated></updated>"
        b'<site_status project_id="p" site_id="s" status_id="green"/>'
        b"</current_status>"
    )
    with pytest.raises(ValueError, match="missing <updated><datetime>"):
        parse_aurora(body)


def test_parse_missing_site_status_raises() -> None:
    body = _xml(include_site=False)
    with pytest.raises(ValueError, match="missing <site_status>"):
        parse_aurora(body)


def test_parse_malformed_xml_raises() -> None:
    with pytest.raises(ValueError, match="xml parse failure"):
        parse_aurora(b"<not-xml")


def test_parse_unparseable_datetime_raises() -> None:
    body = _xml(dt="totally not a date")
    with pytest.raises(ValueError, match="unparseable datetime"):
        parse_aurora(body)


# ---------- Pinned fixture ----------


def test_parse_pinned_fixture(fixtures_dir: Path) -> None:
    body = (fixtures_dir / "aurora" / "current_status_sample.xml").read_bytes()
    ts, status, detail = parse_aurora(body)
    # Fixture captured 2026-05-25T23:30:32+0000
    assert ts == int(datetime(2026, 5, 25, 23, 30, 32, tzinfo=UTC).timestamp())
    assert status == "green"
    assert detail == "project:SAMNET:site:SAMNET:CRK2"


# ---------- Smoke: parser does NOT use shared parse_ts (carve-out lives here) ----------


def test_parser_source_does_not_import_parse_ts() -> None:
    """Compact +0000 must be handled at parser level (BGS pattern)."""
    from pathlib import Path as _P

    src = _P("observatory/pollers/aurorawatch/parser.py").read_text()
    assert "parse_ts" not in src, (
        "AuroraWatch parser must NOT import parse_ts — it owns the compact-tz carve-out"
    )
    assert "parsedate_to_datetime" in src, "carve-out (email.utils.parsedate_to_datetime) required"
    assert "defusedxml" in src, "must use defusedxml.ElementTree"
    assert "xml.etree" not in src, "must NOT import stdlib xml.etree"
