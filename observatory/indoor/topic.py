"""Pure parsing of ESPHome indoor-node MQTT topics + payloads (Phase 14).

ESPHome (with ``mqtt: topic_prefix: indoor/<node>``, ``discovery: false``)
publishes each sensor to::

    indoor/<node>/sensor/<metric>/state    payload = a bare number, e.g. "822"

plus ``indoor/<node>/status`` (online/offline LWT) and a chatty
``indoor/<node>/debug`` log topic. Only the ``sensor/.../state`` topics carry
readings; everything else is ignored by the subscriber.

No I/O here — all functions are pure so they unit-test without MQTT or a DB.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

# ESPHome sensor name (topic segment) → indoor_air column.
# The current node emits co2/temperature/humidity/pressure; gas/illuminance are
# mapped ahead of richer nodes so no code change is needed when they arrive.
METRIC_COLUMNS: dict[str, str] = {
    "co2": "co2_ppm",
    "temperature": "temp_c",
    "humidity": "humidity_pct",
    "pressure": "pressure_hpa",
    "gas": "gas_index",
    "illuminance": "lux",
}

# Columns that must be stored as INTEGER (the rest are REAL).
_INT_COLUMNS: frozenset[str] = frozenset({"co2_ppm", "wifi_rssi"})

# Physically possible ranges, from each sensor's own datasheet with headroom
# (SCD-41: 0-40000 ppm; BME280: -40..85 C, 300-1100 hPa). Anything outside is a
# fault or a forgery, not a reading (security audit 2026-10-20, M4). Humidity
# runs to 105 so rounding can never drop a genuine 100 % reading.
_PLAUSIBLE: dict[str, tuple[float, float]] = {
    "co2_ppm": (0, 40_000),
    "temp_c": (-50, 85),
    "humidity_pct": (0, 105),
    "pressure_hpa": (300, 1100),
    "gas_index": (0, 1_000_000),
    "lux": (0, 200_000),
}


# Room ids become node_id rows and dashboard labels: lowercase slug only, so a
# misbehaving or compromised node cannot invent arbitrary ids (audit F20).
_NODE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")


@dataclass(frozen=True)
class IndoorMetric:
    """One parsed sensor-state topic."""

    node_id: str
    column: str  # target indoor_air column
    metric: str  # raw ESPHome metric name (topic segment)


def parse_metric_topic(
    topic: str, allowed_nodes: frozenset[str] | None = None
) -> IndoorMetric | None:
    """Parse ``indoor/<node>/sensor/<metric>/state`` → IndoorMetric, else None.

    Returns None for status/debug topics, unknown metrics, malformed topics,
    or a node id that is malformed or (when ``allowed_nodes`` is given) not
    allowlisted — the caller drops those silently.
    """
    parts = topic.split("/")
    if len(parts) != 5:
        return None
    prefix, node_id, kind, metric, leaf = parts
    if prefix != "indoor" or kind != "sensor" or leaf != "state":
        return None
    if not _NODE_ID.match(node_id):
        return None
    if allowed_nodes is not None and node_id not in allowed_nodes:
        return None
    column = METRIC_COLUMNS.get(metric)
    if column is None:
        return None
    return IndoorMetric(node_id=node_id, column=column, metric=metric)


def coerce_value(column: str, raw: str) -> float | int | None:
    """Coerce a payload string to the column's type; None on non-numeric.

    ESPHome publishes "nan" when a sensor read fails — that, any other
    unparseable payload, and any non-finite or physically impossible value map
    to None so the column is left NULL.
    """
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    # NaN and +/-inf alike: round(inf) raises OverflowError, which used to kill
    # the indoor subscriber task (security audit M4).
    if not math.isfinite(value):
        return None
    low, high = _PLAUSIBLE.get(column, (-math.inf, math.inf))
    if not low <= value <= high:
        return None
    if column in _INT_COLUMNS:
        return round(value)
    return value
