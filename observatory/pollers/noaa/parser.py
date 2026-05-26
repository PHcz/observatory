"""NOAA SWPC parsers: Kp index, solar wind, GOES X-ray flare class.

Three independent parsers, one per endpoint, sharing nothing but the
``ValueError``-on-malformed-input contract:

  - ``parse_kp(body)`` returns ``(ts, estimated_kp)`` from the LAST entry.
    ``time_tag`` is naive ISO (no Z, no offset) and is treated as UTC at
    the parser level (carve-out — strict ``parse_ts`` is deliberately NOT
    routed through; mirrors BGS pubDate handling in Phase 04-04).

  - ``parse_solar_wind(body)`` returns ``(ts, speed_kms)`` from the LAST
    data row of the CSV-as-JSON payload. Row 0 is the header
    ``[time_tag, density, speed, temperature]``; data rows are
    string-typed. ``time_tag`` uses a SPACE separator (``2026-05-25
    23:27:00.000``) and is naive UTC — handled inline.

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
from datetime import UTC, datetime

from observatory.pollers._parse_ts import parse_ts

LONG_BAND = "0.1-0.8nm"

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


def parse_solar_wind(body: bytes | str) -> tuple[int, float]:
    """Return ``(ts, speed_kms)`` from the LAST data row of the CSV-as-JSON payload.

    Row 0 is the header. Speed is column index 2. ``time_tag`` uses a
    space separator and is naive UTC.

    Raises ``ValueError`` on header-only payload, JSON decode error, or
    missing column.
    """
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError(f"sw: not JSON: {exc}") from exc
    if not isinstance(data, list) or len(data) < 2:
        raise ValueError("sw: header-only or empty payload")
    last = data[-1]
    try:
        time_tag = str(last[0])
        speed = float(last[2])
    except (IndexError, TypeError, ValueError) as exc:
        raise ValueError(f"sw: malformed last row {last!r}: {exc}") from exc
    # Space separator + naive UTC; datetime.fromisoformat in 3.11+ accepts space.
    try:
        dt = datetime.fromisoformat(time_tag)
    except ValueError as exc:
        raise ValueError(f"sw: bad time_tag {time_tag!r}: {exc}") from exc
    ts = int(dt.replace(tzinfo=UTC).timestamp())
    return ts, speed


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
