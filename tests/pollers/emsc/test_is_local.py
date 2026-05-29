"""Phase 8.5 UI-18: EMSC poller computes is_local via haversine + radius.

Mirrors tests/pollers/usgs/test_is_local.py cases against the EMSC
event-construction code path.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

import observatory.pollers._http as _http_mod
import observatory.pollers._write as _write_mod
import observatory.pollers.emsc.__main__ as emsc_main_mod
from observatory.pollers.emsc.__main__ import main as emsc_main


def _feature(unid: str, lat: float, lon: float, time_iso: str = "2026-01-01T00:00:00Z") -> dict:
    return {
        "type": "Feature",
        "properties": {
            "unid": unid,
            "time": time_iso,
            "mag": 4.5,
            "lat": lat,
            "lon": lon,
            "depth": 5.0,
            "flynn_region": "X",
        },
        "geometry": {"type": "Point", "coordinates": [lon, lat, 5.0]},
    }


def _wrap(features: list[dict]) -> bytes:
    return json.dumps({"type": "FeatureCollection", "features": features}).encode()


def _install_db(monkeypatch: pytest.MonkeyPatch, tmp_db: Path) -> None:
    def _conn(_path: str | None = None) -> sqlite3.Connection:
        c = sqlite3.connect(str(tmp_db), isolation_level=None)
        c.execute("PRAGMA busy_timeout=5000")
        return c

    monkeypatch.setattr(_write_mod, "get_write_conn", _conn)


def _get_is_local(tmp_db: Path, ext_id: str) -> int:
    c = sqlite3.connect(str(tmp_db))
    try:
        row = c.execute(
            "SELECT is_local FROM earthquakes WHERE external_id = ?", (ext_id,)
        ).fetchone()
    finally:
        c.close()
    assert row is not None, f"no row for {ext_id}"
    return int(row[0])


def test_paris_not_local_at_default_radius(monkeypatch: pytest.MonkeyPatch, tmp_db: Path) -> None:
    body = _wrap([_feature("em_paris", 48.8566, 2.3522)])
    monkeypatch.setattr(_http_mod, "fetch", lambda url, *, source: body)
    monkeypatch.setattr(emsc_main_mod, "fetch", lambda url, *, source: body)
    _install_db(monkeypatch, tmp_db)
    assert emsc_main() == 0
    assert _get_is_local(tmp_db, "em_paris") == 0


def test_brighton_local_at_default_radius(monkeypatch: pytest.MonkeyPatch, tmp_db: Path) -> None:
    body = _wrap([_feature("em_brighton", 50.8225, -0.1372)])
    monkeypatch.setattr(_http_mod, "fetch", lambda url, *, source: body)
    monkeypatch.setattr(emsc_main_mod, "fetch", lambda url, *, source: body)
    _install_db(monkeypatch, tmp_db)
    assert emsc_main() == 0
    assert _get_is_local(tmp_db, "em_brighton") == 1


def test_radius_bump_flips_paris_to_local(monkeypatch: pytest.MonkeyPatch, tmp_db: Path) -> None:
    import observatory.config as _config_mod

    for mod in (_config_mod, emsc_main_mod, _write_mod):
        monkeypatch.setattr(mod.settings, "observatory_local_radius_km", 400.0, raising=False)

    body = _wrap([_feature("em_paris_bump", 48.8566, 2.3522)])
    monkeypatch.setattr(_http_mod, "fetch", lambda url, *, source: body)
    monkeypatch.setattr(emsc_main_mod, "fetch", lambda url, *, source: body)
    _install_db(monkeypatch, tmp_db)
    assert emsc_main() == 0
    assert _get_is_local(tmp_db, "em_paris_bump") == 1


def test_boundary_distance_inclusive(monkeypatch: pytest.MonkeyPatch, tmp_db: Path) -> None:
    import observatory.config as _config_mod
    from observatory.pollers._geo import haversine_km

    target_lat, target_lon = 50.8225, -0.1372
    dist = haversine_km(51.5074, -0.1278, target_lat, target_lon)
    for mod in (_config_mod, emsc_main_mod, _write_mod):
        monkeypatch.setattr(mod.settings, "observatory_local_radius_km", dist, raising=False)

    body = _wrap([_feature("em_boundary", target_lat, target_lon)])
    monkeypatch.setattr(_http_mod, "fetch", lambda url, *, source: body)
    monkeypatch.setattr(emsc_main_mod, "fetch", lambda url, *, source: body)
    _install_db(monkeypatch, tmp_db)
    assert emsc_main() == 0
    assert _get_is_local(tmp_db, "em_boundary") == 1
