"""USGS GeoJSON parser.

Note: USGS ``time`` field is INTEGER MILLISECONDS since epoch (not ISO).
We divide by 1000 directly; we do NOT route through parse_ts (which
expects ISO). See 04-RESEARCH.md Pitfall 1.

Per-item resilience (CONTEXT-locked partial-parse contract):
  Bad items log WARNING with truncated raw bytes and increment the
  failure counter; the caller (__main__) decides whether the failure
  ratio exceeds POLLER_PARSE_FAILURE_THRESHOLD via
  _write.compute_parse_outcome.
"""

from __future__ import annotations

import json

import structlog

from observatory.pollers._types import EarthquakeEvent

log = structlog.get_logger(__name__)

_RAW_TRUNCATE = 200


def parse_usgs(body: bytes | str) -> tuple[list[EarthquakeEvent], int]:
    """Parse USGS GeoJSON FeatureCollection into normalized events.

    Returns ``(events, parse_failures)``. Structural failures
    (json.JSONDecodeError, missing ``features`` of wrong shape) still
    raise — those are payload-level and land on ``parse_fail`` via the
    __main__ exception handler. Per-item failures are absorbed: counted
    + WARNING-logged with a ``raw`` field truncated to <=200 chars.

    USGS-specific quirks (per 04-RESEARCH live capture):
      - ``time`` is integer milliseconds since epoch -> divide by 1000
      - ``id`` (top-level on the feature) is the external_id
      - ``geometry.coordinates`` is ``[longitude, latitude, depth_km]``
      - ``properties.place`` is optional
      - ``coordinates`` may omit depth (length 2) -> depth_km = None
    """
    data = json.loads(body)
    features = data.get("features", [])
    out: list[EarthquakeEvent] = []
    failures = 0
    for feat in features:
        try:
            props = feat["properties"]
            geom = feat["geometry"]
            coords = geom["coordinates"]  # [lon, lat, depth_km]
            ts_ms = props["time"]
            out.append(
                EarthquakeEvent(
                    source="usgs",
                    external_id=feat["id"],
                    ts=int(ts_ms // 1000),
                    magnitude=float(props["mag"]),
                    depth_km=float(coords[2]) if len(coords) >= 3 else None,
                    latitude=float(coords[1]),
                    longitude=float(coords[0]),
                    place=props.get("place"),
                )
            )
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            failures += 1
            raw = json.dumps(feat)[:_RAW_TRUNCATE]
            log.warning(
                "usgs_item_parse_failed",
                source="usgs",
                error=f"{type(exc).__name__}: {exc}",
                raw=raw,
            )
    return out, failures
