"""RED tests for NOAA combined poller __main__ (Phase 05-02).

Scenarios:
  - all 3 endpoints succeed -> exit 0, ONE space_weather row, poller_runs.status='success'
  - 1 endpoint network-fails -> exit 0, row with NULL field, status='partial', error_summary
  - all 3 endpoints fail -> exit 1, NO space_weather row, status='transient_fail'
  - 1 endpoint parse-fails -> exit 0, partial row, error_summary contains 'parse:'
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import observatory.pollers.noaa.__main__ as noaa_main
from observatory.db import connection as db_conn_mod
from observatory.pollers._http import RetriesExhausted

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def patched_db(monkeypatch: pytest.MonkeyPatch, tmp_db: Path) -> Path:
    """Point get_conn / get_write_conn at the tmp_db for the duration of the test."""

    def _factory(_path: str | None = None) -> sqlite3.Connection:
        conn = sqlite3.connect(str(tmp_db), isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    monkeypatch.setattr(db_conn_mod, "get_conn", _factory)
    monkeypatch.setattr(db_conn_mod, "get_write_conn", _factory)
    import observatory.pollers._write as _write_mod

    monkeypatch.setattr(_write_mod, "get_write_conn", _factory, raising=False)
    return tmp_db


def _fetch_bodies(fixtures_dir: Path) -> dict[str, bytes]:
    return {
        "kp": (fixtures_dir / "noaa" / "kp_sample.json").read_bytes(),
        "sw": (fixtures_dir / "noaa" / "solar_wind_sample.json").read_bytes(),
        "xray": (fixtures_dir / "noaa" / "xray_sample.json").read_bytes(),
    }


def _install_fetch(
    monkeypatch: pytest.MonkeyPatch,
    *,
    kp: bytes | Exception,
    sw: bytes | Exception,
    xray: bytes | Exception,
) -> None:
    """Replace observatory.pollers.noaa.__main__.fetch with a router by URL."""
    from observatory.config import settings as _s

    routes = {
        _s.poller_noaa_kp_url: kp,
        _s.poller_noaa_solar_wind_url: sw,
        _s.poller_noaa_xray_url: xray,
    }

    def _fake_fetch(url: str, *, source: str) -> bytes:
        result = routes[url]
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(noaa_main, "fetch", _fake_fetch)


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


def test_main_all_three_succeed(
    monkeypatch: pytest.MonkeyPatch, patched_db: Path, fixtures_dir: Path
) -> None:
    bodies = _fetch_bodies(fixtures_dir)
    _install_fetch(monkeypatch, kp=bodies["kp"], sw=bodies["sw"], xray=bodies["xray"])

    rc = noaa_main.main()
    assert rc == 0

    conn = sqlite3.connect(str(patched_db))
    conn.row_factory = sqlite3.Row
    sw_rows = conn.execute("SELECT * FROM space_weather").fetchall()
    assert len(sw_rows) == 1
    row = sw_rows[0]
    assert row["kp_index"] == pytest.approx(2.0)
    assert row["solar_wind_kms"] == pytest.approx(403.0)
    assert row["flare_class"] == "C4.6"
    assert row["flare_peak_ts"] == 1779748920

    pr_rows = conn.execute("SELECT * FROM poller_runs WHERE source='noaa'").fetchall()
    assert len(pr_rows) == 1
    assert pr_rows[0]["status"] == "success"
    assert pr_rows[0]["error_summary"] is None
    conn.close()


def test_main_solar_wind_network_fails_writes_partial(
    monkeypatch: pytest.MonkeyPatch, patched_db: Path, fixtures_dir: Path
) -> None:
    bodies = _fetch_bodies(fixtures_dir)
    _install_fetch(
        monkeypatch,
        kp=bodies["kp"],
        sw=RetriesExhausted("connection reset"),
        xray=bodies["xray"],
    )

    rc = noaa_main.main()
    assert rc == 0

    conn = sqlite3.connect(str(patched_db))
    conn.row_factory = sqlite3.Row
    sw_rows = conn.execute("SELECT * FROM space_weather").fetchall()
    assert len(sw_rows) == 1
    row = sw_rows[0]
    assert row["kp_index"] == pytest.approx(2.0)
    assert row["solar_wind_kms"] is None
    assert row["flare_class"] == "C4.6"

    pr = conn.execute("SELECT * FROM poller_runs WHERE source='noaa'").fetchone()
    assert pr["status"] == "partial"
    assert pr["error_summary"] is not None
    assert "sw:network" in pr["error_summary"]
    conn.close()


def test_main_xray_parse_fail_writes_partial(
    monkeypatch: pytest.MonkeyPatch, patched_db: Path, fixtures_dir: Path
) -> None:
    bodies = _fetch_bodies(fixtures_dir)
    _install_fetch(
        monkeypatch,
        kp=bodies["kp"],
        sw=bodies["sw"],
        xray=b"not json at all",
    )

    rc = noaa_main.main()
    assert rc == 0

    conn = sqlite3.connect(str(patched_db))
    conn.row_factory = sqlite3.Row
    sw_rows = conn.execute("SELECT * FROM space_weather").fetchall()
    assert len(sw_rows) == 1
    row = sw_rows[0]
    assert row["flare_class"] is None
    assert row["flare_peak_ts"] is None
    assert row["kp_index"] == pytest.approx(2.0)

    pr = conn.execute("SELECT * FROM poller_runs WHERE source='noaa'").fetchone()
    assert pr["status"] == "partial"
    assert "xray:parse" in pr["error_summary"]
    conn.close()


def test_main_all_three_fail_no_row(monkeypatch: pytest.MonkeyPatch, patched_db: Path) -> None:
    _install_fetch(
        monkeypatch,
        kp=RetriesExhausted("kp net"),
        sw=RetriesExhausted("sw net"),
        xray=RetriesExhausted("xray net"),
    )

    rc = noaa_main.main()
    assert rc == 1

    conn = sqlite3.connect(str(patched_db))
    conn.row_factory = sqlite3.Row
    sw_rows = conn.execute("SELECT * FROM space_weather").fetchall()
    assert len(sw_rows) == 0
    pr = conn.execute("SELECT * FROM poller_runs WHERE source='noaa'").fetchone()
    assert pr["status"] == "transient_fail"
    assert pr["error_summary"] is not None
    assert "kp:network" in pr["error_summary"]
    assert "sw:network" in pr["error_summary"]
    assert "xray:network" in pr["error_summary"]
    conn.close()
