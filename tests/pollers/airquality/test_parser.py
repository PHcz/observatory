"""RED tests for the Open-Meteo air-quality parser (Phase 11, OAQ-01).

These import `parse_air_quality` + the AirQualitySnapshot dataclass, which Wave 1
(plan 11-02) creates. Until then these fail at import (expected RED).

The fixture is the pinned real Open-Meteo AQ response captured in Wave 0 (London
sentinel); tests assert on its STRUCTURE and the naive-local -> UTC offset math,
not on hard values (so a hand-authored small fixture would also satisfy them).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from observatory.pollers.airquality.parser import parse_air_quality

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "airquality" / "sample.json"


def _fixture_bytes() -> bytes:
    return FIXTURE.read_bytes()


def _fixture_dict() -> dict:
    return json.loads(_fixture_bytes())


def test_parses_current_to_snapshot() -> None:
    snapshot, meta = parse_air_quality(_fixture_bytes())
    # AQI + 5 pollutants + UV
    assert snapshot.european_aqi is not None
    for field in ("pm2_5", "pm10", "nitrogen_dioxide", "ozone", "sulphur_dioxide"):
        assert hasattr(snapshot, field)
    assert hasattr(snapshot, "uv_index")
    # 6 pollen fields
    for field in (
        "alder_pollen",
        "birch_pollen",
        "grass_pollen",
        "mugwort_pollen",
        "olive_pollen",
        "ragweed_pollen",
    ):
        assert hasattr(snapshot, field)
    assert isinstance(snapshot.ts, int)
    # meta freshness anchor
    assert "utc_offset_seconds" in meta
    assert "timezone" in meta
    assert isinstance(meta["fetched_at"], int)


def test_applies_utc_offset() -> None:
    data = _fixture_dict()
    off = int(data["utc_offset_seconds"])
    snapshot, _meta = parse_air_quality(_fixture_bytes())
    local = data["current"]["time"]
    expected = int(datetime.fromisoformat(local).replace(tzinfo=UTC).timestamp()) - off
    assert snapshot.ts == expected


def test_null_field_preserved_as_none() -> None:
    data = _fixture_dict()
    data["current"]["pm2_5"] = None
    snapshot, _meta = parse_air_quality(json.dumps(data).encode())
    assert snapshot.pm2_5 is None


def test_missing_current_raises_valueerror() -> None:
    data = _fixture_dict()
    del data["current"]
    with pytest.raises(ValueError):
        parse_air_quality(json.dumps(data).encode())


def test_bad_json_raises_valueerror() -> None:
    with pytest.raises(ValueError):
        parse_air_quality(b"not json at all")
