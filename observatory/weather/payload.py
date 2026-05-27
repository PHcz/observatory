"""Pimoroni Enviro Weather payload parser (Phase 3-01).

Strict pydantic v2 models for the JSON shape published by Pimoroni's stock
firmware to topic ``enviro/<nickname>``. Field aliases translate firmware
names (temperature, humidity, pressure, light, voltage) to schema columns
(temp_c, humidity_pct, pressure_hpa, lux, battery_v) — locked in
03-CONTEXT.md §Schema reconciliation.

Extra firmware fields (wind_speed, wind_direction, rain, rain_per_second)
are silently ignored — the Weather variant doesn't have those sensors but
a future RJ11-expanded board would. ``extra='ignore'`` on both models keeps
the parser future-proof against firmware additions while remaining strict
on type drift of known fields.

Missing ``voltage`` parses to ``battery_v=None``; all other readings are
required and will raise ``pydantic.ValidationError`` if absent or malformed.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class WeatherPayload(BaseModel):
    """The ``readings`` dict — sensor values with column-name aliases."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    temp_c: float = Field(alias="temperature")
    humidity_pct: float = Field(alias="humidity")
    pressure_hpa: float = Field(alias="pressure")
    lux: float = Field(alias="light")
    battery_v: float | None = Field(default=None, alias="voltage")


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
