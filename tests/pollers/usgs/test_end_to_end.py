"""USGS poller end-to-end tests — fetch monkeypatched, real SQLite + parser.

Closes POLL-01 e2e contract, QA-01 fixture replay slice, and the partial-parse
flow (CONTEXT-locked compute_parse_outcome integration).
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
import observatory.pollers.usgs.__main__ as usgs_main
from observatory.pollers._http import (
    CrossHostRedirect,
    ResponseTooLarge,
    RetriesExhausted,
)


def _install_db(monkeypatch: pytest.MonkeyPatch, tmp_db: Path) -> None:
    """Route _write.get_write_conn to the test DB (autocommit isolation)."""

    def _conn(_path: str | None = None) -> sqlite3.Connection:
        c = sqlite3.connect(str(tmp_db), isolation_level=None)
        c.execute("PRAGMA busy_timeout=5000")
        return c

    monkeypatch.setattr(_write_mod, "get_write_conn", _conn)


def _make_feature(fid: str, *, drop_mag: bool = False) -> dict[str, object]:
    props: dict[str, object] = {"time": 1779725577904, "place": "X"}
    if not drop_mag:
        props["mag"] = 4.9
    return {
        "type": "Feature",
        "id": fid,
        "properties": props,
        "geometry": {"type": "Point", "coordinates": [10.0, 20.0, 5.0]},
    }


def _wrap(features: list[dict[str, object]]) -> bytes:
    return json.dumps({"type": "FeatureCollection", "features": features}).encode()


# ---------- Happy path against pinned fixture ----------


def test_e2e_against_fixture_writes_events(
    monkeypatch: pytest.MonkeyPatch,
    tmp_db: Path,
    load_eq_fixture: Callable[[str], bytes],
) -> None:
    body = load_eq_fixture("usgs/sample_4_5_day.json")
    monkeypatch.setattr(_http_mod, "fetch", lambda url, *, source: body)
    monkeypatch.setattr(usgs_main, "fetch", lambda url, *, source: body)
    _install_db(monkeypatch, tmp_db)

    rc = usgs_main.main()
    assert rc == 0

    c = sqlite3.connect(str(tmp_db))
    try:
        cnt = c.execute("SELECT COUNT(*) FROM earthquakes WHERE source='usgs'").fetchone()[0]
        assert cnt == 9
        status = c.execute(
            "SELECT status FROM poller_runs WHERE source='usgs' ORDER BY id DESC LIMIT 1"
        ).fetchone()[0]
        assert status == "success"
    finally:
        c.close()


def test_e2e_dedup_on_second_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_db: Path,
    load_eq_fixture: Callable[[str], bytes],
) -> None:
    body = load_eq_fixture("usgs/sample_4_5_day.json")
    monkeypatch.setattr(_http_mod, "fetch", lambda url, *, source: body)
    monkeypatch.setattr(usgs_main, "fetch", lambda url, *, source: body)
    _install_db(monkeypatch, tmp_db)

    rc1 = usgs_main.main()
    rc2 = usgs_main.main()
    assert rc1 == 0
    assert rc2 == 0

    c = sqlite3.connect(str(tmp_db))
    try:
        # second poller_runs row: fetched=N (events parsed from body),
        # written=0 because dedup absorbed everything.
        row = c.execute(
            "SELECT events_fetched, events_written FROM poller_runs "
            "WHERE source='usgs' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row[0] >= 1
        assert row[1] == 0
    finally:
        c.close()


# ---------- Failure modes ----------


def test_e2e_network_failure_exits_nonzero(monkeypatch: pytest.MonkeyPatch, tmp_db: Path) -> None:
    def boom(url: str, *, source: str) -> bytes:
        raise RetriesExhausted("simulated network failure")

    monkeypatch.setattr(usgs_main, "fetch", boom)
    _install_db(monkeypatch, tmp_db)

    rc = usgs_main.main()
    assert rc != 0

    c = sqlite3.connect(str(tmp_db))
    try:
        row = c.execute(
            "SELECT status, error_summary FROM poller_runs "
            "WHERE source='usgs' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row[0] == "transient_fail"
        assert "simulated" in (row[1] or "")
    finally:
        c.close()


def test_e2e_response_too_large_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch, tmp_db: Path
) -> None:
    def boom(url: str, *, source: str) -> bytes:
        raise ResponseTooLarge("over cap")

    monkeypatch.setattr(usgs_main, "fetch", boom)
    _install_db(monkeypatch, tmp_db)

    rc = usgs_main.main()
    assert rc != 0

    c = sqlite3.connect(str(tmp_db))
    try:
        status = c.execute(
            "SELECT status FROM poller_runs WHERE source='usgs' ORDER BY id DESC LIMIT 1"
        ).fetchone()[0]
        assert status == "transient_fail"
    finally:
        c.close()


def test_e2e_cross_host_redirect_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch, tmp_db: Path
) -> None:
    def boom(url: str, *, source: str) -> bytes:
        raise CrossHostRedirect("off-host")

    monkeypatch.setattr(usgs_main, "fetch", boom)
    _install_db(monkeypatch, tmp_db)

    rc = usgs_main.main()
    assert rc != 0


def test_e2e_parse_failure_exits_nonzero(monkeypatch: pytest.MonkeyPatch, tmp_db: Path) -> None:
    monkeypatch.setattr(usgs_main, "fetch", lambda url, *, source: b"not json at all")
    _install_db(monkeypatch, tmp_db)

    rc = usgs_main.main()
    assert rc != 0

    c = sqlite3.connect(str(tmp_db))
    try:
        status = c.execute(
            "SELECT status FROM poller_runs WHERE source='usgs' ORDER BY id DESC LIMIT 1"
        ).fetchone()[0]
        assert status == "parse_fail"
    finally:
        c.close()


# ---------- Partial-parse: under / over threshold ----------


def test_e2e_partial_parse_under_threshold_succeeds(
    monkeypatch: pytest.MonkeyPatch, tmp_db: Path
) -> None:
    # 8 good + 2 bad = ratio 0.2 < 0.5 default threshold => success
    features = [_make_feature(f"good_{i}") for i in range(8)]
    features += [_make_feature("bad_1", drop_mag=True), _make_feature("bad_2", drop_mag=True)]
    body = _wrap(features)
    monkeypatch.setattr(usgs_main, "fetch", lambda url, *, source: body)
    _install_db(monkeypatch, tmp_db)

    with capture_logs() as logs:
        rc = usgs_main.main()
    assert rc == 0

    c = sqlite3.connect(str(tmp_db))
    try:
        cnt = c.execute("SELECT COUNT(*) FROM earthquakes WHERE source='usgs'").fetchone()[0]
        assert cnt == 8
        row = c.execute(
            "SELECT status, events_fetched, events_written FROM poller_runs "
            "WHERE source='usgs' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row[0] == "success"
        assert row[1] == 8
        assert row[2] == 8
    finally:
        c.close()

    warn_count = sum(1 for e in logs if e.get("log_level") == "warning")
    assert warn_count == 2


def test_e2e_partial_parse_over_threshold_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_db: Path
) -> None:
    # 2 good + 8 bad = ratio 0.8 > 0.5 threshold => parse_fail, write 0
    features = [_make_feature(f"good_{i}") for i in range(2)]
    features += [_make_feature(f"bad_{i}", drop_mag=True) for i in range(8)]
    body = _wrap(features)
    monkeypatch.setattr(usgs_main, "fetch", lambda url, *, source: body)
    _install_db(monkeypatch, tmp_db)

    with capture_logs() as logs:
        rc = usgs_main.main()
    assert rc != 0

    c = sqlite3.connect(str(tmp_db))
    try:
        cnt = c.execute("SELECT COUNT(*) FROM earthquakes WHERE source='usgs'").fetchone()[0]
        assert cnt == 0
        row = c.execute(
            "SELECT status, error_summary FROM poller_runs "
            "WHERE source='usgs' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row[0] == "parse_fail"
        summary = row[1] or ""
        # ratio appears in summary as 0.80 or 8/10
        assert ("0.80" in summary) or ("8/10" in summary)
    finally:
        c.close()

    # ERROR-level event emitted with the ratio context
    errors = [e for e in logs if e.get("log_level") == "error"]
    assert any(("0.80" in str(e.get("summary", ""))) or (e.get("failures") == 8) for e in errors)
