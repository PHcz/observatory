"""Pimoroni Enviro Weather payload parser (Phase 3-01).

Strict pydantic v2 models for the JSON shape published by Pimoroni's stock
firmware to topic ``enviro/<nickname>``. Field aliases translate firmware
names (temperature, humidity, pressure, luminance, voltage) to schema columns
(temp_c, humidity_pct, pressure_hpa, lux, battery_v) — locked in
03-CONTEXT.md §Schema reconciliation.

NOTE: The luminance field name was verified against the actual firmware
shipped to the operator on 2026-05-28; earlier research (03-RESEARCH.md)
predicted ``light`` based on a different firmware version. Real key is
``luminance`` per pimoroni/enviro main branch (enviro/boards/weather.py).

Extra firmware fields (wind_speed, wind_direction, rain, rain_per_second)
are silently ignored — the Weather variant doesn't have anemometer / rain
gauge attached in the bench config; an RJ11-expanded outdoor board may
populate them later. ``extra='ignore'`` on both models keeps the parser
future-proof against firmware additions while remaining strict on type
drift of known fields.

Missing ``voltage`` parses to ``battery_v=None`` — the Weather board's
firmware doesn't include voltage in MQTT publishes for AA-powered units;
the value is logged locally on the SD card. All other readings are
required and will raise ``pydantic.ValidationError`` if absent or malformed.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class WeatherPayload(BaseModel):
    """The ``readings`` dict — sensor values with column-name aliases."""

    # No Infinity/NaN, and BME280/LTR-559 physical ranges with headroom (security
    # audit 2026-10-20, M4): a stored Infinity is re-emitted by FastAPI as
    # `Infinity`, which is not valid JSON and breaks the dashboard parser. Bounds
    # sit well outside 35k rows of real history (3.7-35.8 C, humidity to exactly
    # 100.0, 995-1034 hPa, 0-3688 lux); humidity runs to 105 so rounding cannot
    # drop a genuine overnight 100 %.
    model_config = ConfigDict(extra="ignore", populate_by_name=True, allow_inf_nan=False)

    temp_c: float = Field(alias="temperature", ge=-50, le=85)
    humidity_pct: float = Field(alias="humidity", ge=0, le=105)
    pressure_hpa: float = Field(alias="pressure", ge=300, le=1100)
    lux: float = Field(alias="luminance", ge=0, le=200_000)
    battery_v: float | None = Field(default=None, alias="voltage", ge=0, le=10)


class WeatherEnvelope(BaseModel):
    """The full Pimoroni MQTT message envelope.

    ``timestamp`` is kept as the raw ISO 8601 string — epoch conversion is
    the writer's job (Plan 03-02) so this parser stays purely structural.
    """

    model_config = ConfigDict(extra="ignore")

    nickname: str
    model: str | None = None
    uid: str | None = None
    timestamp: str
    readings: WeatherPayload


def parse_envelope(raw: bytes | str) -> WeatherEnvelope:
    """Strict-parse a Pimoroni MQTT payload.

    Raises ``pydantic.ValidationError`` on any drift: missing required
    fields, wrong types, or invalid JSON bytes.
    """
    return WeatherEnvelope.model_validate_json(raw)
