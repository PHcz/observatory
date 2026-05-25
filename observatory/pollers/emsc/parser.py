"""EMSC FDSNWS GeoJSON parser.

Uses ``properties.unid`` as ``external_id`` per CONTEXT decision (== feature.id in
practice on captured payloads, but the property is the canonical EMSC identifier).
Uses ``properties.lat/lon/depth`` (NOT geometry.coordinates) per CONTEXT — props is
the authoritative value; coordinates uses negative-down-positive convention for depth.

Per-item resilience (CONTEXT-locked partial-parse contract):
    Bad items (including ``ParseError`` from ``parse_ts`` on a malformed/naive time)
    log a WARNING with truncated raw bytes and increment the failure counter; the
    caller decides outcome via ``_write.compute_parse_outcome``.

Structural failures (``json.JSONDecodeError``, missing top-level ``features`` is
absorbed via ``.get``) still propagate so ``__main__`` lands them as ``parse_fail``.
"""

from __future__ import annotations

import json

import structlog

from observatory.pollers._parse_ts import ParseError, parse_ts
from observatory.pollers._types import EarthquakeEvent

log = structlog.get_logger(__name__)

_RAW_TRUNCATE = 200


def parse_emsc(body: bytes) -> tuple[list[EarthquakeEvent], int]:
    """Convert an EMSC FDSNWS GeoJSON response into normalized EarthquakeEvents.

    Returns ``(events, parse_failures)``. ParseError from ``parse_ts`` IS-A
    ``ValueError`` so the ``ValueError`` branch catches it; the explicit listing
    is for grep-readability.
    """
    data = json.loads(body)
    features = data.get("features", [])
    out: list[EarthquakeEvent] = []
    failures = 0
    for feat in features:
        try:
            props = feat["properties"]
            depth = props.get("depth")
            out.append(
                EarthquakeEvent(
                    source="emsc",
                    external_id=props["unid"],
                    ts=parse_ts(props["time"]),
                    magnitude=float(props["mag"]),
                    depth_km=float(depth) if depth is not None else None,
                    latitude=float(props["lat"]),
                    longitude=float(props["lon"]),
                    place=props.get("flynn_region"),
                )
            )
        except (KeyError, TypeError, ValueError, ParseError) as exc:
            failures += 1
            raw = json.dumps(feat)[:_RAW_TRUNCATE]
            log.warning(
                "emsc_item_parse_failed",
                source="emsc",
                error=f"{type(exc).__name__}: {exc}",
                raw=raw,
            )
    return out, failures
