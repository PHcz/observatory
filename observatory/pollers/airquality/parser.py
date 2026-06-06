"""Current-object parser for the Open-Meteo air-quality response (Phase 11, OAQ-01).

Unlike the forecast feed (column-oriented parallel arrays), the air-quality
``current=`` request returns a SINGLE ``current`` object with one scalar per
variable — no zipping needed. This parser pulls those scalars into a single
``AirQualitySnapshot`` (replace-on-fetch cache, migration 0006 ``air_quality``).

Timestamp carve-out: ``current.time`` is a naive local wall-clock ISO without an
offset (e.g. ``2026-06-07T00:00``). To store the project-standard UTC epoch we
parse the naive string as if UTC then subtract ``utc_offset_seconds`` — the same
documented carve-out as ForecastHourly/Daily, NOAA naive-UTC and BGS pubDate
(STATE 05-03 / 04-04); deliberately NOT routed through the strict shared ISO
helper.

Null-tolerant: every measurement is read with ``.get`` so a field absent under
``current`` (or emitted as ``null``) becomes ``None`` on the snapshot.

Parser-strict contract: any structural problem (missing ``current`` /
``utc_offset_seconds`` key, bad JSON) raises ``ValueError`` so the oneshot
``__main__`` can catch one exception type and write a ``parse_fail`` audit row.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime

from observatory.pollers._types import AirQualitySnapshot

_FIELDS = (
    "european_aqi",
    "pm2_5",
    "pm10",
    "nitrogen_dioxide",
    "ozone",
    "sulphur_dioxide",
    "uv_index",
    "alder_pollen",
    "birch_pollen",
    "grass_pollen",
    "mugwort_pollen",
    "olive_pollen",
    "ragweed_pollen",
)


def _local_naive_to_utc_epoch(iso: str, offset_seconds: int) -> int:
    """Naive-local wall-clock ISO -> UTC epoch, via the utc_offset carve-out."""
    return int(datetime.fromisoformat(iso).replace(tzinfo=UTC).timestamp()) - offset_seconds


def parse_air_quality(body: bytes) -> tuple[AirQualitySnapshot, dict[str, int | str]]:
    """Parse an Open-Meteo air-quality response into a snapshot + meta.

    Returns ``(snapshot, meta)`` where ``meta`` carries ``utc_offset_seconds``
    (int), ``timezone`` (str) and ``fetched_at`` (int). Raises ``ValueError`` on a
    missing ``current``/``utc_offset_seconds`` key or bad JSON.
    """
    try:
        data = json.loads(body)
        off = int(data["utc_offset_seconds"])
        cur = data["current"]
        snapshot = AirQualitySnapshot(
            ts=_local_naive_to_utc_epoch(cur["time"], off),
            **{field: cur.get(field) for field in _FIELDS},
        )
        meta: dict[str, int | str] = {
            "utc_offset_seconds": off,
            "timezone": str(data["timezone"]),
            "fetched_at": int(time.time()),
        }
    except (KeyError, TypeError, IndexError, json.JSONDecodeError) as exc:
        raise ValueError(f"malformed Open-Meteo air-quality response: {exc}") from exc

    return snapshot, meta
