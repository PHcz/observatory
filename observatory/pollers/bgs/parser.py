"""BGS RSS parser — converts MhSeismology.xml into ``list[EarthquakeEvent]``.

Closes POLL-03 and resolves three CONTEXT/RESEARCH issues:

1. **Open Question 1 — naive pubDate.** BGS emits RFC 822 timestamps
   without a timezone marker (e.g. ``"Sun, 24 May 2026 20:10:46"``).
   We parse via :func:`email.utils.parsedate_to_datetime` and explicitly
   assign ``tzinfo=UTC`` at the parser level when the result is naive.
   We deliberately do NOT route through the shared strict ISO helper
   in :mod:`observatory.pollers` (which raises on naive datetimes) —
   the BGS UTC-assumption carve-out lives here, not in the shared layer.

2. **Open Question 2 — http vs https.** The https probe ran 2026-05-25
   (see ``tests/pollers/bgs/HTTPS_PROBE_RESULT.md``) and BGS supports
   https; the URL default in :mod:`observatory.config` already points
   at https://. No carve-out lives in :mod:`observatory.pollers._http`.

3. **Pitfall 3 — no <guid>.** BGS items have no ``<guid>`` element.
   We derive the unique ``external_id`` from the per-event ``<link>``
   URL via :data:`LINK_ID_RE` (the 14-digit ``YYYYMMDDHHmmss`` slug).

Contract:
    ``parse_bgs(body) -> (events, parse_failures)``

Per-item resilience (closes checker WARNING 1 for BGS):
    Items with no matching link slug, items missing ``Magnitude:`` in
    the description, and any per-item exception increment
    ``parse_failures`` and emit a WARNING with a truncated raw dump.
    Structural failures (not-XML) propagate as
    :class:`defusedxml.ElementTree.ParseError` (sub-class of stdlib
    ``xml.etree.ElementTree.ParseError``). XML attacks (billion-laughs,
    external entities) are blocked by defusedxml at parse time.
"""

from __future__ import annotations

import re
from datetime import UTC
from email.utils import parsedate_to_datetime

import defusedxml.ElementTree as ET
import structlog

from observatory.pollers._types import EarthquakeEvent

log = structlog.get_logger(__name__)

GEO_NS = {"geo": "http://www.w3.org/2003/01/geo/wgs84_pos#"}
LINK_ID_RE = re.compile(r"/recent_events/(\d{14})\.html")
DEPTH_RE = re.compile(r"Depth:\s*(\d+(?:\.\d+)?)\s*km", re.IGNORECASE)
MAG_RE = re.compile(r"Magnitude:\s*([-+]?\d+(?:\.\d+)?)", re.IGNORECASE)
LOCATION_RE = re.compile(r"Location:\s*([^;]+?)\s*;", re.IGNORECASE)

_RAW_TRUNC = 200


def _raw(item: ET.Element) -> str:
    """Return a truncated XML serialization of an item for log context."""
    try:
        # defusedxml.ElementTree.tostring lacks stubs (ignore_missing_imports);
        # explicit str() pins the return type for mypy strict.
        return str(ET.tostring(item, encoding="unicode"))[:_RAW_TRUNC]
    except Exception:
        return repr(item)[:_RAW_TRUNC]


def parse_bgs(body: bytes | str) -> tuple[list[EarthquakeEvent], int]:
    """Parse BGS RSS feed body into normalized events + per-item failure count.

    Raises ``xml.etree.ElementTree.ParseError`` on structural failure.
    """
    root = ET.fromstring(body)
    events: list[EarthquakeEvent] = []
    failures = 0
    for item in root.findall("./channel/item"):
        try:
            # external_id from <link> regex (no <guid> in BGS feed)
            link = (item.findtext("link") or "").strip()
            m_id = LINK_ID_RE.search(link)
            if not m_id:
                log.warning(
                    "bgs_item_skipped_missing_link",
                    reason="link did not match recent_events slug",
                    raw=_raw(item),
                )
                failures += 1
                continue
            external_id = m_id.group(1)

            # pubDate -> ts (naive RFC 822 assumed UTC; aware respected)
            pub = (item.findtext("pubDate") or "").strip()
            dt = parsedate_to_datetime(pub)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            ts = int(dt.astimezone(UTC).timestamp())

            # magnitude (required) + depth (optional) + place from description
            desc = item.findtext("description") or ""
            m_mag = MAG_RE.search(desc)
            if not m_mag:
                log.warning(
                    "bgs_item_skipped_missing_magnitude",
                    reason="description had no 'Magnitude:' token",
                    raw=_raw(item),
                )
                failures += 1
                continue
            magnitude = float(m_mag.group(1))

            m_depth = DEPTH_RE.search(desc)
            depth_km = float(m_depth.group(1)) if m_depth else None

            m_loc = LOCATION_RE.search(desc)
            place = m_loc.group(1).strip() if m_loc else None

            # geo:lat / geo:long
            lat_raw = item.findtext("geo:lat", namespaces=GEO_NS)
            lon_raw = item.findtext("geo:long", namespaces=GEO_NS)
            latitude = float(lat_raw) if lat_raw is not None else float("nan")
            longitude = float(lon_raw) if lon_raw is not None else float("nan")

            events.append(
                EarthquakeEvent(
                    source="bgs",
                    external_id=external_id,
                    ts=ts,
                    magnitude=magnitude,
                    depth_km=depth_km,
                    latitude=latitude,
                    longitude=longitude,
                    place=place,
                )
            )
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            log.warning(
                "bgs_item_parse_error",
                error=f"{type(exc).__name__}: {exc}",
                raw=_raw(item),
            )
            failures += 1
            continue
    return events, failures
