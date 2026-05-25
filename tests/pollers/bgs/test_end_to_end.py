"""End-to-end tests for `python -m observatory.pollers.bgs`.

Mirrors the 04-02 USGS / 04-03 EMSC e2e structure: monkeypatches fetch +
get_write_conn, runs main(), asserts on earthquakes + poller_runs rows.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

import pytest
from structlog.testing import capture_logs

import observatory.pollers._http as _http_mod
import observatory.pollers._write as _write_mod
from observatory.pollers._http import RetriesExhausted
from observatory.pollers.bgs.__main__ import main as bgs_main

# ---------- Synthetic feed builder (mirrors test_parser.py shape) ----------


def _wrap(items_xml: str) -> bytes:
    return (
        b'<?xml version="1.0"?>\n'
        b'<rss version="2.0" xmlns:geo="http://www.w3.org/2003/01/geo/wgs84_pos#">\n'
        b"<channel>\n" + items_xml.encode() + b"</channel>\n</rss>\n"
    )


def _item(
    *,
    slug: str = "20260524200750",
    link_host: str = "http://earthquakes.bgs.ac.uk",
    pub_date: str = "Sun, 24 May 2026 20:10:46",
    lat: str = "50.080",
    lon: str = "0.682",
    description: str | None = None,
) -> str:
    if description is None:
        description = (
            "Origin date/time: Sun, 24 May 2026 20:10:46 ; Location: ENGLISH CHANNEL ; "
            "Lat/long: 50.080,0.682 ; Depth: 14 km ; Magnitude:  2.2"
        )
    link = f"{link_host}/earthquakes/recent_events/{slug}.html"
    return (
        "<item>\n"
        f"<title>UK Earthquake alert : M  2.2 :PLACE</title>\n"
        f"<description>{description}</description>\n"
        f"<link>{link}</link>\n"
        f"<pubDate>{pub_date}</pubDate>\n"
        "<category>EQUK</category>\n"
        f"<geo:lat>{lat}</geo:lat>\n"
        f"<geo:long>{lon}</geo:long>\n"
        "</item>\n"
    )


# ---------- Fixtures ----------


@pytest.fixture
def patched_db(monkeypatch: pytest.MonkeyPatch, tmp_db: Path) -> Path:
    """Redirect _write.get_write_conn to a fresh tmp DB pre-loaded with both migrations."""

    def _conn(_db_path: str | None = None) -> sqlite3.Connection:
        c = sqlite3.connect(str(tmp_db), isolation_level=None)
        c.execute("PRAGMA foreign_keys=ON")
        return c

    monkeypatch.setattr(_write_mod, "get_write_conn", _conn)
    return tmp_db


def _install_fetch(monkeypatch: pytest.MonkeyPatch, body_or_exc: bytes | Exception) -> None:
    def fake_fetch(url: str, *, source: str, **_kw: object) -> bytes:
        if isinstance(body_or_exc, Exception):
            raise body_or_exc
        return body_or_exc

    import observatory.pollers.bgs.__main__ as _main_mod

    monkeypatch.setattr(_http_mod, "fetch", fake_fetch)
    monkeypatch.setattr(_main_mod, "fetch", fake_fetch)


# ---------- Tests ----------


def test_e2e_against_fixture_writes_events(
    monkeypatch: pytest.MonkeyPatch,
    patched_db: Path,
    load_eq_fixture: Callable[[str], bytes],
) -> None:
    body = load_eq_fixture("bgs/sample_recent.xml")
    _install_fetch(monkeypatch, body)
    rc = bgs_main()
    assert rc == 0
    conn = sqlite3.connect(str(patched_db))
    n = conn.execute("SELECT COUNT(*) FROM earthquakes WHERE source='bgs'").fetchone()[0]
    assert n >= 1
    status = conn.execute(
        "SELECT status FROM poller_runs WHERE source='bgs' ORDER BY id DESC LIMIT 1"
    ).fetchone()[0]
    assert status == "success"
    conn.close()


def test_e2e_dedup_on_second_run(
    monkeypatch: pytest.MonkeyPatch,
    patched_db: Path,
    load_eq_fixture: Callable[[str], bytes],
) -> None:
    body = load_eq_fixture("bgs/sample_recent.xml")
    _install_fetch(monkeypatch, body)
    assert bgs_main() == 0
    first = (
        sqlite3.connect(str(patched_db))
        .execute("SELECT COUNT(*) FROM earthquakes WHERE source='bgs'")
        .fetchone()[0]
    )
    assert bgs_main() == 0
    conn = sqlite3.connect(str(patched_db))
    n = conn.execute("SELECT COUNT(*) FROM earthquakes WHERE source='bgs'").fetchone()[0]
    assert n == first  # dedup absorbed second run
    runs = conn.execute(
        "SELECT events_written FROM poller_runs WHERE source='bgs' ORDER BY id ASC"
    ).fetchall()
    assert len(runs) == 2
    assert runs[0][0] == first
    assert runs[1][0] == 0
    conn.close()


def test_e2e_network_failure_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch, patched_db: Path
) -> None:
    _install_fetch(monkeypatch, RetriesExhausted("simulated"))
    rc = bgs_main()
    assert rc == 1
    conn = sqlite3.connect(str(patched_db))
    row = conn.execute(
        "SELECT status, error_summary FROM poller_runs WHERE source='bgs' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row[0] == "transient_fail"
    assert "simulated" in (row[1] or "")
    conn.close()


def test_e2e_parse_failure_exits_nonzero(monkeypatch: pytest.MonkeyPatch, patched_db: Path) -> None:
    _install_fetch(monkeypatch, b"<not-xml")
    rc = bgs_main()
    assert rc == 1
    conn = sqlite3.connect(str(patched_db))
    status = conn.execute(
        "SELECT status FROM poller_runs WHERE source='bgs' ORDER BY id DESC LIMIT 1"
    ).fetchone()[0]
    assert status == "parse_fail"
    conn.close()


def test_e2e_partial_parse_under_threshold_succeeds(
    monkeypatch: pytest.MonkeyPatch, patched_db: Path
) -> None:
    """8 good + 2 bad (missing link match) -> exit 0, 8 rows written, 2 WARNING lines."""
    good_items = "".join(_item(slug=f"2026052420{i:04d}") for i in range(8))
    bad_items = (
        "<item>\n"
        "<title>bad 1</title>\n"
        "<description>no magnitude ; Location: X ; Lat/long: 0,0</description>\n"
        "<link>http://example.com/wrong/shape.html</link>\n"
        "<pubDate>Sun, 24 May 2026 20:10:46</pubDate>\n"
        "<geo:lat>0</geo:lat><geo:long>0</geo:long>\n"
        "</item>\n"
        "<item>\n"
        "<title>bad 2</title>\n"
        "<description>also no mag ; Location: Y ; Lat/long: 0,0</description>\n"
        "<link>http://example.com/another.html</link>\n"
        "<pubDate>Sun, 24 May 2026 20:10:46</pubDate>\n"
        "<geo:lat>0</geo:lat><geo:long>0</geo:long>\n"
        "</item>\n"
    )
    body = _wrap(good_items + bad_items)
    _install_fetch(monkeypatch, body)
    with capture_logs() as logs:
        rc = bgs_main()
    assert rc == 0
    conn = sqlite3.connect(str(patched_db))
    n = conn.execute("SELECT COUNT(*) FROM earthquakes WHERE source='bgs'").fetchone()[0]
    assert n == 8
    status = conn.execute(
        "SELECT status FROM poller_runs WHERE source='bgs' ORDER BY id DESC LIMIT 1"
    ).fetchone()[0]
    assert status == "success"
    conn.close()
    warnings = [e for e in logs if e.get("log_level") == "warning"]
    assert len(warnings) >= 2


def test_e2e_partial_parse_over_threshold_fails(
    monkeypatch: pytest.MonkeyPatch, patched_db: Path
) -> None:
    """2 good + 8 bad -> exit 1, 0 rows written, poller_runs parse_fail with ratio in summary."""
    good_items = "".join(_item(slug=f"2026052420{i:04d}") for i in range(2))
    bad_items = "".join(
        (
            "<item>\n"
            f"<title>bad {i}</title>\n"
            "<description>no magnitude ; Location: X ; Lat/long: 0,0</description>\n"
            f"<link>http://example.com/wrong/{i}.html</link>\n"
            "<pubDate>Sun, 24 May 2026 20:10:46</pubDate>\n"
            "<geo:lat>0</geo:lat><geo:long>0</geo:long>\n"
            "</item>\n"
        )
        for i in range(8)
    )
    body = _wrap(good_items + bad_items)
    _install_fetch(monkeypatch, body)
    rc = bgs_main()
    assert rc == 1
    conn = sqlite3.connect(str(patched_db))
    n = conn.execute("SELECT COUNT(*) FROM earthquakes WHERE source='bgs'").fetchone()[0]
    assert n == 0
    row = conn.execute(
        "SELECT status, error_summary FROM poller_runs WHERE source='bgs' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row[0] == "parse_fail"
    assert row[1] is not None
    assert "0.80" in row[1] or "8/10" in row[1]
    conn.close()
