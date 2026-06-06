"""RED tests for the Open-Meteo column-zip forecast parser (Phase 10, FCAST-01).

These import `parse_forecast` + the ForecastHourly/ForecastDaily dataclasses,
which Wave 1 (plan 10-02) creates. Until then these fail at import (expected RED).

The fixture is the pinned real Open-Meteo response captured in Wave 0; tests
assert on its STRUCTURE and the naive-local -> UTC offset math, not on a hard
count (so a hand-authored small fixture would also satisfy them).
"""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from observatory.pollers._types import (
    ForecastDaily,
    ForecastHourly,
)
from observatory.pollers.forecast.parser import parse_forecast

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "forecast" / "sample.json"


def _fixture_bytes() -> bytes:
    return FIXTURE.read_bytes()


def _fixture_dict() -> dict:
    return json.loads(_fixture_bytes())


def test_parses_columns_to_rows() -> None:
    data = _fixture_dict()
    hourly, daily, meta = parse_forecast(_fixture_bytes())
    assert len(hourly) == len(data["hourly"]["time"])
    assert len(daily) == len(data["daily"]["time"])
    assert all(isinstance(h, ForecastHourly) for h in hourly)
    assert all(isinstance(d, ForecastDaily) for d in daily)


def test_applies_utc_offset() -> None:
    data = _fixture_dict()
    off = int(data["utc_offset_seconds"])
    hourly, _daily, _meta = parse_forecast(_fixture_bytes())
    first_local = data["hourly"]["time"][0]
    expected = int(datetime.fromisoformat(first_local).replace(tzinfo=UTC).timestamp()) - off
    assert hourly[0].ts == expected


def test_meta_has_offset_tz_fetched_at() -> None:
    _hourly, _daily, meta = parse_forecast(_fixture_bytes())
    assert "utc_offset_seconds" in meta
    assert "timezone" in meta
    assert isinstance(meta["fetched_at"], int)


def test_ragged_arrays_raise_valueerror() -> None:
    data = _fixture_dict()
    # Make temperature_2m shorter than time -> ragged.
    data["hourly"]["temperature_2m"] = data["hourly"]["temperature_2m"][:-1]
    with pytest.raises(ValueError):
        parse_forecast(json.dumps(data).encode())


def test_missing_key_raises_valueerror() -> None:
    data = _fixture_dict()
    del data["utc_offset_seconds"]
    with pytest.raises(ValueError):
        parse_forecast(json.dumps(data).encode())


def test_null_precip_preserved_as_none() -> None:
    data = copy.deepcopy(_fixture_dict())
    data["hourly"]["precipitation_probability"][0] = None
    hourly, _daily, _meta = parse_forecast(json.dumps(data).encode())
    assert hourly[0].precip_prob_pct is None
