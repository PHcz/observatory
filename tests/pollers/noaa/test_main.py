"""RED tests for NOAA combined poller __main__ (Phase 05-02).

Scenarios:
  - all endpoints succeed -> exit 0, ONE space_weather row, poller_runs.status='success'
  - 1 endpoint network-fails / 404s -> exit 0, row with NULL field, status='partial'
  - all endpoints fail -> exit 1, NO space_weather row, status='transient_fail'
  - 1 endpoint parse-fails -> exit 0, partial row, error_summary contains 'parse:'
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import httpx
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


_FIXTURES = {
    "kp": "kp_sample.json",
    "sw": "rtsw_wind_sample.json",
    "imf": "rtsw_mag_sample.json",
    "protons": "protons_sample.json",
    "scales": "scales_sample.json",
    "xray": "xray_sample.json",
}


def _urls() -> dict[str, str]:
    from observatory.config import settings as _s

    return {
        "kp": _s.poller_noaa_kp_url,
        "sw": _s.poller_noaa_solar_wind_url,
        "imf": _s.poller_noaa_mag_url,
        "protons": _s.poller_noaa_protons_url,
        "scales": _s.poller_noaa_scales_url,
        "xray": _s.poller_noaa_xray_url,
    }


def _install_fetch(
    monkeypatch: pytest.MonkeyPatch,
    fixtures_dir: Path,
    **overrides: bytes | Exception,
) -> None:
    """Route noaa_main.fetch by URL: fixture bodies unless overridden per label."""
    routes: dict[str, bytes | Exception] = {}
    for label, url in _urls().items():
        routes[url] = overrides.get(label, (fixtures_dir / "noaa" / _FIXTURES[label]).read_bytes())

    def _fake_fetch(url: str, *, source: str) -> bytes:
        result = routes[url]
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(noaa_main, "fetch", _fake_fetch)


def _http_error(status: int, url: str) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", url)
    return httpx.HTTPStatusError(
        f"{status}", request=request, response=httpx.Response(status, request=request)
    )


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


def test_main_all_endpoints_succeed(
    monkeypatch: pytest.MonkeyPatch, patched_db: Path, fixtures_dir: Path
) -> None:
    _install_fetch(monkeypatch, fixtures_dir)

    rc = noaa_main.main()
    assert rc == 0

    conn = sqlite3.connect(str(patched_db))
    conn.row_factory = sqlite3.Row
    sw_rows = conn.execute("SELECT * FROM space_weather").fetchall()
    assert len(sw_rows) == 1
    row = sw_rows[0]
    assert row["kp_index"] == pytest.approx(2.0)
    assert row["solar_wind_kms"] == pytest.approx(352.1)
    assert row["solar_wind_density"] == pytest.approx(5.99)
    assert row["imf_bz_nt"] == pytest.approx(-6.16)
    assert row["imf_bt_nt"] is not None
    assert row["proton_flux_10mev"] == pytest.approx(0.2756652235984802)
    assert (row["noaa_scale_r"], row["noaa_scale_s"], row["noaa_scale_g"]) == (0, 0, 0)
    assert row["flare_class"] == "C4.6"
    assert row["flare_peak_ts"] == 1779748920

    pr_rows = conn.execute("SELECT * FROM poller_runs WHERE source='noaa'").fetchall()
    assert len(pr_rows) == 1
    assert pr_rows[0]["status"] == "success"
    assert pr_rows[0]["error_summary"] is None
    conn.close()


def test_main_retired_endpoint_404_is_partial_not_a_crash(
    monkeypatch: pytest.MonkeyPatch, patched_db: Path, fixtures_dir: Path
) -> None:
    """NOAA retired the old solar-wind URL in 2026-09. The 404 escaped
    _safe_fetch and crashed the whole poll, so Kp and flares froze too --
    the space-weather panel showed 2026-09-09 data for six weeks."""
    _install_fetch(monkeypatch, fixtures_dir, sw=_http_error(404, "https://x/retired.json"))

    assert noaa_main.main() == 0

    conn = sqlite3.connect(str(patched_db))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM space_weather").fetchone()
    assert row["solar_wind_kms"] is None
    assert row["kp_index"] == pytest.approx(2.0)
    assert row["flare_class"] == "C4.6"
    pr = conn.execute("SELECT * FROM poller_runs WHERE source='noaa'").fetchone()
    assert pr["status"] == "partial"
    assert "sw:http:404" in pr["error_summary"]
    conn.close()


def test_main_solar_wind_network_fails_writes_partial(
    monkeypatch: pytest.MonkeyPatch, patched_db: Path, fixtures_dir: Path
) -> None:
    _install_fetch(monkeypatch, fixtures_dir, sw=RetriesExhausted("connection reset"))

    rc = noaa_main.main()
    assert rc == 0

    conn = sqlite3.connect(str(patched_db))
    conn.row_factory = sqlite3.Row
    sw_rows = conn.execute("SELECT * FROM space_weather").fetchall()
    assert len(sw_rows) == 1
    row = sw_rows[0]
    assert row["kp_index"] == pytest.approx(2.0)
    assert row["solar_wind_kms"] is None
    assert row["solar_wind_density"] is None
    assert row["flare_class"] == "C4.6"

    pr = conn.execute("SELECT * FROM poller_runs WHERE source='noaa'").fetchone()
    assert pr["status"] == "partial"
    assert pr["error_summary"] is not None
    assert "sw:network" in pr["error_summary"]
    conn.close()


def test_main_xray_parse_fail_writes_partial(
    monkeypatch: pytest.MonkeyPatch, patched_db: Path, fixtures_dir: Path
) -> None:
    _install_fetch(monkeypatch, fixtures_dir, xray=b"not json at all")

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


def test_main_all_endpoints_fail_no_row(
    monkeypatch: pytest.MonkeyPatch, patched_db: Path, fixtures_dir: Path
) -> None:
    _install_fetch(
        monkeypatch,
        fixtures_dir,
        **{label: RetriesExhausted(f"{label} net") for label in _FIXTURES},
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
    conn.close()
