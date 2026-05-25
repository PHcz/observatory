"""End-to-end tests for `python -m observatory.pollers.emsc`.

Mirrors the 04-02 USGS e2e structure: monkeypatches fetch + get_write_conn,
runs main(), asserts on earthquakes + poller_runs rows.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from pathlib import Path

import pytest
from structlog.testing import capture_logs

import observatory.pollers._http as _http_mod
import observatory.pollers._write as _write_mod
from observatory.pollers._http import RetriesExhausted
from observatory.pollers.emsc.__main__ import main as emsc_main


def _make_feature(
    *,
    unid: str,
    time_str: str = "2026-05-25T19:49:24.0Z",
    mag: float = 3.0,
    depth: float | None = 17.0,
    lat: float = -8.14,
    lon: float = 117.79,
    flynn: str = "TEST REGION",
) -> dict:
    return {
        "type": "Feature",
        "id": unid,
        "geometry": {"type": "Point", "coordinates": [lon, lat, -(depth or 0.0)]},
        "properties": {
            "time": time_str,
            "flynn_region": flynn,
            "lat": lat,
            "lon": lon,
            "depth": depth,
            "mag": mag,
            "unid": unid,
        },
    }


def _wrap(features: list[dict]) -> bytes:
    return json.dumps({"type": "FeatureCollection", "features": features}).encode("utf-8")


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

    # Patch BOTH the source module and the main-module re-import alias
    import observatory.pollers.emsc.__main__ as _main_mod

    monkeypatch.setattr(_http_mod, "fetch", fake_fetch)
    monkeypatch.setattr(_main_mod, "fetch", fake_fetch)
    # main() calls configure_logging() which would re-install processors and
    # break capture_logs(). No-op it under tests — the autouse conftest fixture
    # already configured structlog for capture.
    monkeypatch.setattr(_main_mod, "configure_logging", lambda *a, **kw: None)


def test_e2e_against_fixture_writes_events(
    monkeypatch: pytest.MonkeyPatch,
    patched_db: Path,
    load_eq_fixture: Callable[[str], bytes],
) -> None:
    body = load_eq_fixture("emsc/sample_pastday.json")
    _install_fetch(monkeypatch, body)
    rc = emsc_main()
    assert rc == 0
    conn = sqlite3.connect(str(patched_db))
    n = conn.execute("SELECT COUNT(*) FROM earthquakes WHERE source='emsc'").fetchone()[0]
    assert n == 200, f"expected 200 EMSC events from pinned fixture, got {n}"
    status = conn.execute(
        "SELECT status FROM poller_runs WHERE source='emsc' ORDER BY id DESC LIMIT 1"
    ).fetchone()[0]
    assert status == "success"
    conn.close()


def test_e2e_dedup_on_second_run(
    monkeypatch: pytest.MonkeyPatch,
    patched_db: Path,
    load_eq_fixture: Callable[[str], bytes],
) -> None:
    body = load_eq_fixture("emsc/sample_pastday.json")
    _install_fetch(monkeypatch, body)
    assert emsc_main() == 0
    assert emsc_main() == 0
    conn = sqlite3.connect(str(patched_db))
    n = conn.execute("SELECT COUNT(*) FROM earthquakes WHERE source='emsc'").fetchone()[0]
    assert n == 200
    runs = conn.execute(
        "SELECT events_fetched, events_written FROM poller_runs WHERE source='emsc' ORDER BY id ASC"
    ).fetchall()
    assert len(runs) == 2
    assert runs[0] == (200, 200)
    assert runs[1] == (200, 0)
    conn.close()


def test_e2e_network_failure_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch, patched_db: Path
) -> None:
    _install_fetch(monkeypatch, RetriesExhausted("simulated"))
    rc = emsc_main()
    assert rc == 1
    conn = sqlite3.connect(str(patched_db))
    row = conn.execute(
        "SELECT status, error_summary FROM poller_runs WHERE source='emsc' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row[0] == "transient_fail"
    assert "simulated" in (row[1] or "")
    conn.close()


def test_e2e_parse_failure_exits_nonzero(monkeypatch: pytest.MonkeyPatch, patched_db: Path) -> None:
    _install_fetch(monkeypatch, b"not json at all")
    rc = emsc_main()
    assert rc == 1
    conn = sqlite3.connect(str(patched_db))
    status = conn.execute(
        "SELECT status FROM poller_runs WHERE source='emsc' ORDER BY id DESC LIMIT 1"
    ).fetchone()[0]
    assert status == "parse_fail"
    conn.close()


def test_e2e_partial_parse_under_threshold_succeeds(
    monkeypatch: pytest.MonkeyPatch, patched_db: Path
) -> None:
    """8 good + 2 bad (naive time) -> exit 0, 8 rows written, 2 WARNING lines."""
    good = [_make_feature(unid=f"good-{i}") for i in range(8)]
    bad = [_make_feature(unid=f"bad-{i}", time_str="2026-05-25T19:49:24") for i in range(2)]
    body = _wrap(good + bad)
    _install_fetch(monkeypatch, body)
    with capture_logs() as logs:
        rc = emsc_main()
    assert rc == 0
    conn = sqlite3.connect(str(patched_db))
    n = conn.execute("SELECT COUNT(*) FROM earthquakes WHERE source='emsc'").fetchone()[0]
    assert n == 8
    status = conn.execute(
        "SELECT status FROM poller_runs WHERE source='emsc' ORDER BY id DESC LIMIT 1"
    ).fetchone()[0]
    assert status == "success"
    conn.close()
    warnings = [e for e in logs if e.get("log_level") == "warning"]
    assert len(warnings) >= 2


def test_e2e_partial_parse_over_threshold_fails(
    monkeypatch: pytest.MonkeyPatch, patched_db: Path
) -> None:
    """2 good + 8 bad -> exit 1, 0 rows written, poller_runs parse_fail with ratio in summary."""
    good = [_make_feature(unid=f"good-{i}") for i in range(2)]
    bad = [_make_feature(unid=f"bad-{i}", time_str="2026-05-25T19:49:24") for i in range(8)]
    body = _wrap(good + bad)
    _install_fetch(monkeypatch, body)
    rc = emsc_main()
    assert rc == 1
    conn = sqlite3.connect(str(patched_db))
    n = conn.execute("SELECT COUNT(*) FROM earthquakes WHERE source='emsc'").fetchone()[0]
    assert n == 0
    row = conn.execute(
        "SELECT status, error_summary FROM poller_runs WHERE source='emsc' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row[0] == "parse_fail"
    assert row[1] is not None
    # ratio is failures/total = 8/10 = 0.80
    assert "0.80" in row[1] or "8/10" in row[1]
    conn.close()
