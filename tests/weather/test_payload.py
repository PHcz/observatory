"""RED-then-GREEN tests for the Pimoroni Enviro Weather payload parser (Phase 3-01).

Covers the 7 fixture cases authored in 03-00 plus two synthetic invalid-bytes
cases. Tests the field-alias contract locked in 03-CONTEXT.md §Schema
reconciliation: temperature->temp_c, humidity->humidity_pct, pressure->pressure_hpa,
light->lux, voltage->battery_v.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from pydantic import ValidationError

from observatory.weather.payload import (
    WeatherEnvelope,
    WeatherPayload,
    parse_envelope,
)


def test_parses_canonical_payload(load_payload: Callable[[str], bytes]) -> None:
    env = parse_envelope(load_payload("canonical_payload.json"))
    assert isinstance(env, WeatherEnvelope)
    assert env.nickname == "observatory-weather"
    assert isinstance(env.readings, WeatherPayload)
    assert env.readings.temp_c == 18.4
    assert env.readings.humidity_pct == 61.2
    assert env.readings.pressure_hpa == 1012.3
    assert env.readings.lux == 234.5
    assert env.readings.battery_v == 2.7


def test_parses_missing_voltage(load_payload: Callable[[str], bytes]) -> None:
    env = parse_envelope(load_payload("missing_voltage.json"))
    assert env.readings.battery_v is None
    # Other fields still parsed
    assert env.readings.temp_c == 18.6
    assert env.readings.humidity_pct == 60.8


def test_parses_with_wind_rain_extra_fields(load_payload: Callable[[str], bytes]) -> None:
    env = parse_envelope(load_payload("with_wind_rain.json"))
    # Extras must be ignored, not raised
    assert env.readings.temp_c == 19.1
    assert env.readings.battery_v == 2.68
    # Extras should not surface as attributes
    assert not hasattr(env.readings, "wind_speed")
    assert not hasattr(env.readings, "rain")


def test_rejects_no_readings(load_payload: Callable[[str], bytes]) -> None:
    with pytest.raises(ValidationError):
        parse_envelope(load_payload("malformed_no_readings.json"))


def test_rejects_invalid_json() -> None:
    with pytest.raises(ValidationError):
        parse_envelope(b"not json")


def test_rejects_wrong_type() -> None:
    bad = (
        b'{"nickname":"x","timestamp":"2026-01-01T00:00:00Z",'
        b'"readings":{"temperature":"hot","humidity":50.0,'
        b'"pressure":1000.0,"luminance":100.0}}'
    )
    with pytest.raises(ValidationError):
        parse_envelope(bad)


def test_zero_lux_at_night(load_payload: Callable[[str], bytes]) -> None:
    env = parse_envelope(load_payload("zero_lux_night.json"))
    assert env.readings.lux == 0.0
    assert env.readings.lux is not None


def test_cold_temperature_negative(load_payload: Callable[[str], bytes]) -> None:
    env = parse_envelope(load_payload("cold_temperature.json"))
    assert env.readings.temp_c == -3.5


def test_timestamp_returned_as_string(load_payload: Callable[[str], bytes]) -> None:
    env = parse_envelope(load_payload("canonical_payload.json"))
    # Raw ISO 8601 — ts conversion is the writer's job (03-02)
    assert env.timestamp == "2026-05-27T12:00:00Z"
    assert isinstance(env.timestamp, str)


def test_parses_live_firmware_capture(load_payload: Callable[[str], bytes]) -> None:
    """Regression: verbatim capture from the operator's actual Pimoroni Enviro
    Weather board on 2026-05-28 (bench test, AA alkalines, firmware shipped
    pre-flashed). Verifies all field aliases against ground-truth, including:

    - ``luminance`` -> lux (NOT ``light`` — 03-RESEARCH.md predicted wrong key)
    - voltage absent from Weather-board payloads -> battery_v=None
    - extra fields (rain, wind_speed, wind_direction, rain_per_second) ignored
    """
    env = parse_envelope(load_payload("live_firmware_capture.json"))
    assert env.nickname == "observatory-weather"
    assert env.model == "weather"
    assert env.uid == "e6614864d32f9936"
    assert env.timestamp == "2026-05-28T16:35:04Z"
    assert env.readings.temp_c == 27.33
    assert env.readings.humidity_pct == 44.42
    assert env.readings.pressure_hpa == 1018.97
    assert env.readings.lux == 307.47
    assert env.readings.battery_v is None  # Weather board firmware omits voltage
