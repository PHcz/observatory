"""RED tests for NOAA SWPC parser functions (Phase 05-02).

Parsers (to be implemented in observatory.pollers.noaa.parser):
  - parse_kp(body: bytes) -> tuple[int, float]
  - parse_solar_wind(body: bytes) -> tuple[int, float]
  - parse_xray_flare(body: bytes) -> tuple[str, int] | None
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from observatory.pollers.noaa.parser import (
    parse_kp,
    parse_solar_wind,
    parse_xray_flare,
)

# ---------------------------------------------------------------------------
# parse_kp
# ---------------------------------------------------------------------------


def test_parse_kp_returns_last_entry(fixtures_dir: Path) -> None:
    body = (fixtures_dir / "noaa" / "kp_sample.json").read_bytes()
    ts, kp = parse_kp(body)
    # Last entry in fixture: "2026-05-25T23:26:00", estimated_kp=2.00
    assert ts == 1779751560
    assert kp == pytest.approx(2.0)


def test_parse_kp_uses_estimated_kp_not_integer_kp_index(fixtures_dir: Path) -> None:
    # Synthesise a payload where estimated_kp != kp_index to lock the choice
    payload = json.dumps(
        [
            {"time_tag": "2026-05-25T12:00:00", "kp_index": 2, "estimated_kp": 1.67, "kp": "2M"},
            {"time_tag": "2026-05-25T12:01:00", "kp_index": 3, "estimated_kp": 2.67, "kp": "3M"},
        ]
    ).encode()
    ts, kp = parse_kp(payload)
    assert kp == pytest.approx(2.67)
    assert ts > 0


def test_parse_kp_naive_treated_as_utc() -> None:
    # 12:00 UTC = 1779710400
    payload = json.dumps(
        [{"time_tag": "2026-05-25T12:00:00", "kp_index": 0, "estimated_kp": 0.0, "kp": "0Z"}]
    ).encode()
    ts, _ = parse_kp(payload)
    assert ts == 1779710400


def test_parse_kp_empty_raises() -> None:
    with pytest.raises(ValueError):
        parse_kp(b"[]")


def test_parse_kp_not_json_raises() -> None:
    with pytest.raises(ValueError):
        parse_kp(b"not json")


def test_parse_kp_missing_key_raises() -> None:
    payload = json.dumps([{"time_tag": "2026-05-25T12:00:00"}]).encode()
    with pytest.raises(ValueError):
        parse_kp(payload)


# ---------------------------------------------------------------------------
# parse_solar_wind
# ---------------------------------------------------------------------------


def test_parse_solar_wind_returns_last_row(fixtures_dir: Path) -> None:
    body = (fixtures_dir / "noaa" / "solar_wind_sample.json").read_bytes()
    ts, speed = parse_solar_wind(body)
    # Last row: "2026-05-25 23:27:00.000", speed=403.0
    assert ts == 1779751620
    assert speed == pytest.approx(403.0)


def test_parse_solar_wind_speed_is_column_index_2() -> None:
    # Header is [time_tag, density, speed, temperature]; speed at index 2.
    payload = json.dumps(
        [
            ["time_tag", "density", "speed", "temperature"],
            ["2026-05-25 12:00:00.000", "5.0", "350.5", "60000"],
            ["2026-05-25 12:01:00.000", "5.1", "555.5", "61000"],
        ]
    ).encode()
    ts, speed = parse_solar_wind(payload)
    assert speed == pytest.approx(555.5)
    assert ts > 0


def test_parse_solar_wind_header_only_raises() -> None:
    payload = b'[["time_tag","density","speed","temperature"]]'
    with pytest.raises(ValueError):
        parse_solar_wind(payload)


def test_parse_solar_wind_empty_raises() -> None:
    with pytest.raises(ValueError):
        parse_solar_wind(b"[]")


def test_parse_solar_wind_naive_treated_as_utc() -> None:
    payload = json.dumps(
        [
            ["time_tag", "density", "speed", "temperature"],
            ["2026-05-25 12:00:00.000", "5.0", "400.0", "60000"],
        ]
    ).encode()
    ts, _ = parse_solar_wind(payload)
    assert ts == 1779710400


# ---------------------------------------------------------------------------
# parse_xray_flare
# ---------------------------------------------------------------------------


def test_parse_xray_flare_from_fixture(fixtures_dir: Path) -> None:
    body = (fixtures_dir / "noaa" / "xray_sample.json").read_bytes()
    result = parse_xray_flare(body)
    assert result is not None
    flare_class, peak_ts = result
    # Fixture peak in 0.1-0.8nm band: flux=4.62e-06 at 2026-05-25T22:42:00Z -> "C4.6"
    assert flare_class == "C4.6"
    assert peak_ts == 1779748920


def test_parse_xray_flare_filters_to_long_band() -> None:
    # Only short-band entries -> no long-band records -> returns None
    payload = json.dumps(
        [
            {"time_tag": "2026-05-25T12:00:00Z", "flux": 1.0e-06, "energy": "0.05-0.4nm"},
            {"time_tag": "2026-05-25T12:01:00Z", "flux": 2.0e-06, "energy": "0.05-0.4nm"},
        ]
    ).encode()
    assert parse_xray_flare(payload) is None


def test_parse_xray_flare_picks_max_flux_in_long_band() -> None:
    payload = json.dumps(
        [
            {"time_tag": "2026-05-25T12:00:00Z", "flux": 1.0e-06, "energy": "0.1-0.8nm"},
            {"time_tag": "2026-05-25T12:05:00Z", "flux": 9.9e-04, "energy": "0.05-0.4nm"},
            {"time_tag": "2026-05-25T12:05:00Z", "flux": 3.3e-06, "energy": "0.1-0.8nm"},
            {"time_tag": "2026-05-25T12:10:00Z", "flux": 2.0e-06, "energy": "0.1-0.8nm"},
        ]
    ).encode()
    result = parse_xray_flare(payload)
    assert result is not None
    flare_class, peak_ts = result
    assert flare_class == "C3.3"
    # Peak at 12:05 UTC
    assert peak_ts == 1779710700


def test_parse_xray_flare_invalid_json_raises() -> None:
    with pytest.raises(ValueError):
        parse_xray_flare(b"not json")


@pytest.mark.parametrize(
    ("flux", "expected"),
    [
        (1.33e-06, "C1.3"),
        (2.5e-08, "A2.5"),
        (8.7e-04, "X8.7"),
        (9.99e-05, "M9.9"),
        (1.0e-04, "X1.0"),  # boundary: >= 1e-4 is X
        (1.0e-07, "B1.0"),  # boundary: >= 1e-7 is B
        (1.0e-06, "C1.0"),  # boundary: >= 1e-6 is C
        (1.0e-05, "M1.0"),  # boundary: >= 1e-5 is M
    ],
)
def test_parse_xray_flare_class_derivation(flux: float, expected: str) -> None:
    payload = json.dumps(
        [{"time_tag": "2026-05-25T12:00:00Z", "flux": flux, "energy": "0.1-0.8nm"}]
    ).encode()
    result = parse_xray_flare(payload)
    assert result is not None
    flare_class, _peak_ts = result
    assert flare_class == expected
