"""RED tests for NOAA SWPC parser functions (Phase 05-02).

Parsers (to be implemented in observatory.pollers.noaa.parser):
  - parse_kp(body: bytes) -> tuple[int, float]
  - parse_solar_wind(body: bytes) -> tuple[int, float, float | None]
  - parse_imf / parse_proton_flux / parse_noaa_scales (2026-10 additions)
  - parse_xray_flare(body: bytes) -> tuple[str, int] | None
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from observatory.pollers.noaa.parser import (
    parse_imf,
    parse_kp,
    parse_noaa_scales,
    parse_proton_flux,
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


# NOAA retired products/solar-wind/plasma-2-hour.json (404 since 2026-09); the
# replacement is the real-time solar wind (RTSW) feed: a list of dicts, NEWEST
# FIRST, one row per (minute, spacecraft) with only one spacecraft `active`.


def _wind(
    time_tag: str,
    *,
    active: bool = True,
    speed: float | None = 400.0,
    density: float | None = 5.0,
    source: str = "SOLAR1",
) -> dict[str, object]:
    return {
        "time_tag": time_tag,
        "active": active,
        "source": source,
        "proton_speed": speed,
        "proton_density": density,
    }


def test_parse_solar_wind_from_rtsw_fixture(fixtures_dir: Path) -> None:
    body = (fixtures_dir / "noaa" / "rtsw_wind_sample.json").read_bytes()
    ts, speed, density = parse_solar_wind(body)
    # Newest ACTIVE row: 2026-10-20T13:57:00 SOLAR1 352.1 km/s, 5.99 p/cm3. The
    # newer-looking ACE/IMAP rows at the same or later minute are inactive.
    assert ts == 1792504620
    assert speed == pytest.approx(352.1)
    assert density == pytest.approx(5.99)


def test_parse_solar_wind_uses_only_the_active_spacecraft() -> None:
    payload = json.dumps(
        [
            _wind("2026-10-20T13:58:00", active=False, speed=999.0, source="IMAP"),
            _wind("2026-10-20T13:57:00", speed=410.0),
        ]
    ).encode()
    assert parse_solar_wind(payload)[1] == pytest.approx(410.0)


def test_parse_solar_wind_picks_newest_regardless_of_order() -> None:
    payload = json.dumps(
        [
            _wind("2026-10-20T12:00:00", speed=300.0),
            _wind("2026-10-20T13:00:00", speed=500.0),
        ]
    ).encode()
    assert parse_solar_wind(payload)[1] == pytest.approx(500.0)


def test_parse_solar_wind_skips_active_rows_without_speed() -> None:
    payload = json.dumps(
        [
            _wind("2026-10-20T13:58:00", speed=None),
            _wind("2026-10-20T13:57:00", speed=420.0, density=None),
        ]
    ).encode()
    _, speed, density = parse_solar_wind(payload)
    assert speed == pytest.approx(420.0)
    assert density is None


def test_parse_solar_wind_naive_treated_as_utc() -> None:
    payload = json.dumps([_wind("2026-05-25T12:00:00")]).encode()
    assert parse_solar_wind(payload)[0] == 1779710400


@pytest.mark.parametrize(
    "body",
    [b"[]", b"not json", b"{}", json.dumps([_wind("2026-10-20T13:57:00", active=False)]).encode()],
)
def test_parse_solar_wind_without_usable_rows_raises(body: bytes) -> None:
    with pytest.raises(ValueError):
        parse_solar_wind(body)


# ---------------------------------------------------------------------------
# parse_imf -- interplanetary magnetic field (RTSW mag, same shape as wind)
# ---------------------------------------------------------------------------


def test_parse_imf_from_rtsw_fixture(fixtures_dir: Path) -> None:
    body = (fixtures_dir / "noaa" / "rtsw_mag_sample.json").read_bytes()
    ts, bz, bt = parse_imf(body)
    # Newest ACTIVE row is 13:57:00 SOLAR1; the 13:58:01 / 13:57:01 IMAP rows
    # are inactive. Bz is the GSM component -- the one that couples to Earth.
    assert ts == 1792504620
    assert bz == pytest.approx(-6.16)
    assert bt is not None and bt > 0


def test_parse_imf_without_active_rows_raises() -> None:
    payload = json.dumps(
        [{"time_tag": "2026-10-20T13:57:00", "active": False, "bz_gsm": -3.0, "bt": 5.0}]
    ).encode()
    with pytest.raises(ValueError):
        parse_imf(payload)


# ---------------------------------------------------------------------------
# parse_proton_flux -- GOES integral protons, >=10 MeV channel (the S-scale one)
# ---------------------------------------------------------------------------


def test_parse_proton_flux_takes_newest_10mev_reading(fixtures_dir: Path) -> None:
    body = (fixtures_dir / "noaa" / "protons_sample.json").read_bytes()
    ts, flux = parse_proton_flux(body)
    assert ts == 1792504200  # 2026-10-20T13:50:00Z
    assert flux == pytest.approx(0.2756652235984802)


def test_parse_proton_flux_without_10mev_channel_raises() -> None:
    payload = json.dumps(
        [{"time_tag": "2026-10-20T13:50:00Z", "flux": 1.0, "energy": ">=100 MeV"}]
    ).encode()
    with pytest.raises(ValueError):
        parse_proton_flux(payload)


# ---------------------------------------------------------------------------
# parse_noaa_scales -- current R (radio blackout) / S (radiation) / G (geomag)
# ---------------------------------------------------------------------------


def test_parse_noaa_scales_reads_the_current_entry(fixtures_dir: Path) -> None:
    body = (fixtures_dir / "noaa" / "scales_sample.json").read_bytes()
    assert parse_noaa_scales(body) == (0, 0, 0)


def test_parse_noaa_scales_reads_levels_from_key_0_not_yesterday() -> None:
    entry = {"R": {"Scale": "1"}, "S": {"Scale": "2"}, "G": {"Scale": "3"}}
    old = {"R": {"Scale": "5"}, "S": {"Scale": "5"}, "G": {"Scale": "5"}}
    assert parse_noaa_scales(json.dumps({"0": entry, "-1": old}).encode()) == (1, 2, 3)


@pytest.mark.parametrize(
    "body",
    [
        b"[]",
        b"{}",
        b'{"0": {"R": {"Scale": "x"}}}',
        b'{"0": {"R": {"Scale": "9"}, "S": {"Scale": "0"}, "G": {"Scale": "0"}}}',
    ],
)
def test_parse_noaa_scales_rejects_malformed(body: bytes) -> None:
    with pytest.raises(ValueError):
        parse_noaa_scales(body)


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
