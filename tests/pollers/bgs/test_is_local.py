"""Phase 8.5 UI-18: BGS poller hardcodes is_local=True on every event written.

BGS is UK-only by definition; no distance math required. We monkeypatch the
HTTP fetch + writer DB, run the main entry point, then assert every row in
the earthquakes table for source='bgs' carries is_local=1.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import observatory.pollers._http as _http_mod
import observatory.pollers._write as _write_mod
from observatory.pollers.bgs.__main__ import main as bgs_main


def _wrap(items_xml: str) -> bytes:
    return (
        b'<?xml version="1.0"?>\n'
        b'<rss version="2.0" xmlns:geo="http://www.w3.org/2003/01/geo/wgs84_pos#">\n'
        b"<channel>\n" + items_xml.encode() + b"</channel>\n</rss>\n"
    )


def _item(slug: str, lat: str, lon: str) -> str:
    link = f"http://earthquakes.bgs.ac.uk/earthquakes/recent_events/{slug}.html"
    description = (
        f"Origin date/time: Sun, 24 May 2026 20:10:46 ; Location: UK ; "
        f"Lat/long: {lat},{lon} ; Depth: 5 km ; Magnitude:  2.2"
    )
    return (
        "<item>\n"
        "<title>UK Earthquake alert : M 2.2 :PLACE</title>\n"
        f"<description>{description}</description>\n"
        f"<link>{link}</link>\n"
        "<pubDate>Sun, 24 May 2026 20:10:46</pubDate>\n"
        "<category>EQUK</category>\n"
        f"<geo:lat>{lat}</geo:lat>\n"
        f"<geo:long>{lon}</geo:long>\n"
        "</item>\n"
    )


def _install_db(monkeypatch: pytest.MonkeyPatch, tmp_db: Path) -> None:
    def _conn(_path: str | None = None) -> sqlite3.Connection:
        c = sqlite3.connect(str(tmp_db), isolation_level=None)
        c.execute("PRAGMA busy_timeout=5000")
        return c

    monkeypatch.setattr(_write_mod, "get_write_conn", _conn)


def test_bgs_events_always_local(monkeypatch: pytest.MonkeyPatch, tmp_db: Path) -> None:
    """Two BGS events from arbitrary UK lat/lons; both must be is_local=1."""
    body = _wrap(_item("20260101120000", "55.0", "-3.0") + _item("20260102120000", "51.5", "-1.0"))
    monkeypatch.setattr(_http_mod, "fetch", lambda url, *, source: body)
    import observatory.pollers.bgs.__main__ as bgs_main_mod

    monkeypatch.setattr(bgs_main_mod, "fetch", lambda url, *, source: body)
    _install_db(monkeypatch, tmp_db)

    rc = bgs_main()
    assert rc == 0

    c = sqlite3.connect(str(tmp_db))
    try:
        rows = c.execute(
            "SELECT external_id, is_local FROM earthquakes WHERE source='bgs'"
        ).fetchall()
    finally:
        c.close()
    assert len(rows) == 2
    for ext_id, is_local in rows:
        assert is_local == 1, f"BGS event {ext_id} must be is_local=1, got {is_local}"
