"""NOAA SWPC parsers: Kp, solar wind, IMF, protons, NOAA scales, X-ray flare class.

Independent parsers, one per endpoint, sharing nothing but the
``ValueError``-on-malformed-input contract:

  - ``parse_kp(body)`` returns ``(ts, estimated_kp)`` from the LAST entry.
    ``time_tag`` is naive ISO (no Z, no offset) and is treated as UTC at
    the parser level (carve-out — strict ``parse_ts`` is deliberately NOT
    routed through; mirrors BGS pubDate handling in Phase 04-04).

  - ``parse_solar_wind(body)`` / ``parse_imf(body)`` read the real-time
    solar wind (RTSW) plasma and magnetometer feeds -- lists of dicts, one
    row per (minute, spacecraft), newest first, naive-UTC ``time_tag``.
    Only the ``active`` spacecraft's newest row is used. (The old
    ``products/solar-wind/plasma-2-hour.json`` CSV-as-JSON feed was retired
    by NOAA in 2026-09 and returns 404.)

  - ``parse_proton_flux(body)`` -- newest GOES >=10 MeV integral proton flux.

  - ``parse_noaa_scales(body)`` -- current R/S/G NOAA scale levels.

  - ``parse_xray_flare(body)`` returns ``(flare_class, peak_ts)`` or
    ``None``. Filters records to the ``0.1-0.8nm`` long band, picks the
    MAXIMUM ``flux`` value, derives the NOAA class string. ``time_tag``
    has a Z suffix and IS routed through strict ``parse_ts``.

NOAA flare-class scale (long-band peak flux W/m^2):
  A: flux < 1e-7
  B: 1e-7 <= flux < 1e-6
  C: 1e-6 <= flux < 1e-5
  M: 1e-5 <= flux < 1e-4
  X: flux >= 1e-4
  sub-class digit = (flux / class_floor) rounded to 1 decimal.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from typing import Any

from observatory.pollers._parse_ts import parse_ts

LONG_BAND = "0.1-0.8nm"
PROTON_CHANNEL = ">=10 MeV"

# (class_letter, floor) ordered from highest to lowest so first match wins.
_FLARE_CLASSES: tuple[tuple[str, float], ...] = (
    ("X", 1e-4),
    ("M", 1e-5),
    ("C", 1e-6),
    ("B", 1e-7),
)


def parse_kp(body: bytes | str) -> tuple[int, float]:
    """Return ``(ts, estimated_kp)`` from the LAST entry of the Kp 1-min feed.

    Raises ``ValueError`` on empty list, JSON decode error, or missing keys.
    """
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError(f"kp: not JSON: {exc}") from exc
    if not isinstance(data, list) or not data:
        raise ValueError("kp: empty or non-list payload")
    last = data[-1]
    try:
        time_tag = last["time_tag"]
        estimated_kp = float(last["estimated_kp"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"kp: missing/invalid field in last entry: {exc}") from exc
    # time_tag is naive ISO -> treat as UTC (carve-out, NOT parse_ts).
    try:
        dt = datetime.fromisoformat(time_tag)
    except ValueError as exc:
        raise ValueError(f"kp: bad time_tag {time_tag!r}: {exc}") from exc
    ts = int(dt.replace(tzinfo=UTC).timestamp())
    return ts, estimated_kp


def _newest_active(body: bytes | str, label: str, required: str) -> dict[str, Any]:
    """Newest ``active`` row with a non-null ``required`` field from an RTSW feed.

    RTSW feeds list one row per (minute, spacecraft), newest first; exactly one
    spacecraft is ``active`` (the operational source) at any time. Inactive
    rows can be newer than the newest active one, so order is not trusted.
    """
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label}: not JSON: {exc}") from exc
    if not isinstance(data, list):
        raise ValueError(f"{label}: non-list payload")
    rows = [
        r
        for r in data
        if isinstance(r, dict)
        and r.get("active") is True
        and r.get(required) is not None
        and isinstance(r.get("time_tag"), str)
    ]
    if not rows:
        raise ValueError(f"{label}: no active row with {required}")
    return max(rows, key=lambda r: str(r["time_tag"]))


def _naive_utc_ts(time_tag: str, label: str) -> int:
    try:
        dt = datetime.fromisoformat(time_tag)
    except ValueError as exc:
        raise ValueError(f"{label}: bad time_tag {time_tag!r}: {exc}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return int(dt.timestamp())


def _opt_float(value: object, label: str) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}: non-numeric value {value!r}") from exc
    if not math.isfinite(out):
        raise ValueError(f"{label}: non-finite value {value!r}")
    return out


def _req_float(value: object, label: str) -> float:
    out = _opt_float(value, label)
    if out is None:
        raise ValueError(f"{label}: missing value")
    return out


def parse_solar_wind(body: bytes | str) -> tuple[int, float, float | None]:
    """Return ``(ts, speed_kms, density_cm3)`` from the RTSW wind feed."""
    row = _newest_active(body, "sw", "proton_speed")
    speed = _req_float(row["proton_speed"], "sw")
    density = _opt_float(row.get("proton_density"), "sw")
    return _naive_utc_ts(row["time_tag"], "sw"), speed, density


def parse_imf(body: bytes | str) -> tuple[int, float, float | None]:
    """Return ``(ts, bz_gsm_nt, bt_nt)`` from the RTSW magnetometer feed.

    Bz in GSM coordinates is the component that couples to Earth's field:
    sustained negative (southward) Bz is what drives geomagnetic storms.
    """
    row = _newest_active(body, "imf", "bz_gsm")
    bz = _req_float(row["bz_gsm"], "imf")
    return _naive_utc_ts(row["time_tag"], "imf"), bz, _opt_float(row.get("bt"), "imf")


def parse_proton_flux(body: bytes | str) -> tuple[int, float]:
    """Return ``(ts, flux_pfu)`` for the newest GOES >=10 MeV integral proton reading.

    The >=10 MeV channel defines NOAA's S (solar radiation storm) scale;
    10 pfu is S1. High-energy proton events are what neutron monitors and
    muon detectors can see as ground-level enhancements.
    """
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError(f"protons: not JSON: {exc}") from exc
    if not isinstance(data, list):
        raise ValueError("protons: non-list payload")
    rows = [
        r
        for r in data
        if isinstance(r, dict) and r.get("energy") == PROTON_CHANNEL and r.get("flux") is not None
    ]
    if not rows:
        raise ValueError(f"protons: no {PROTON_CHANNEL} readings")
    newest = max(rows, key=lambda r: str(r.get("time_tag")))
    flux = _req_float(newest["flux"], "protons")
    return parse_ts(newest["time_tag"]), flux


def parse_noaa_scales(body: bytes | str) -> tuple[int, int, int]:
    """Return the current ``(R, S, G)`` NOAA space-weather scale levels (0-5).

    The payload is keyed by day offset; ``"0"`` is now (``"-1"`` is the past
    24h, ``"1".."3"`` are predictions).
    """
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError(f"scales: not JSON: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("0"), dict):
        raise ValueError("scales: no current entry")
    current = data["0"]
    levels: list[int] = []
    for key in ("R", "S", "G"):
        try:
            level = int(current[key]["Scale"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"scales: bad {key} entry: {exc}") from exc
        if not 0 <= level <= 5:
            raise ValueError(f"scales: {key} level {level} outside 0-5")
        levels.append(level)
    return levels[0], levels[1], levels[2]


def _derive_flare_class(flux: float) -> str:
    """Map a long-band flux value to the NOAA flare-class string (e.g. ``C4.6``).

    Mantissa is TRUNCATED to one decimal (NOT rounded) so a value like
    ``9.99e-05`` reports as ``M9.9`` rather than crossing the M->X boundary
    via rounding. This matches the plan's behavior spec / NOAA convention
    (the class boundary is determined by the floor, not by rounding the
    mantissa above it).
    """
    for letter, floor in _FLARE_CLASSES:
        if flux >= floor:
            # Truncate to 1 decimal: floor(x * 10) / 10.
            mantissa = int((flux / floor) * 10) / 10
            return f"{letter}{mantissa:.1f}"
    # Below B floor -> A class; floor = 1e-8.
    mantissa = int((flux / 1e-8) * 10) / 10
    return f"A{mantissa:.1f}"


def parse_xray_flare(body: bytes | str) -> tuple[str, int] | None:
    """Return ``(flare_class, peak_ts)`` from the max long-band flux, or ``None``.

    Filters records to the ``0.1-0.8nm`` energy band and picks the entry
    with the maximum ``flux`` field. Returns ``None`` if the filter
    yields no records (e.g. only short-band data).

    Raises ``ValueError`` on JSON decode failure or unparseable peak
    ``time_tag``.
    """
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError(f"xray: not JSON: {exc}") from exc
    if not isinstance(data, list):
        raise ValueError("xray: non-list payload")
    long_band = [r for r in data if isinstance(r, dict) and r.get("energy") == LONG_BAND]
    if not long_band:
        return None
    try:
        peak = max(long_band, key=lambda r: float(r["flux"]))
        flux = float(peak["flux"])
        time_tag = peak["time_tag"]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"xray: malformed long-band record: {exc}") from exc
    flare_class = _derive_flare_class(flux)
    peak_ts = parse_ts(time_tag)
    return flare_class, peak_ts
