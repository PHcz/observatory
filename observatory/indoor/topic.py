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


@dataclass(frozen=True)
class IndoorMetric:
    """One parsed sensor-state topic."""

    node_id: str
    column: str  # target indoor_air column
    metric: str  # raw ESPHome metric name (topic segment)


def parse_metric_topic(topic: str) -> IndoorMetric | None:
    """Parse ``indoor/<node>/sensor/<metric>/state`` → IndoorMetric, else None.

    Returns None for status/debug topics, unknown metrics, malformed topics,
    or an empty node id — the caller drops those silently.
    """
    parts = topic.split("/")
    if len(parts) != 5:
        return None
    prefix, node_id, kind, metric, leaf = parts
    if prefix != "indoor" or kind != "sensor" or leaf != "state":
        return None
    if not node_id:
        return None
    column = METRIC_COLUMNS.get(metric)
    if column is None:
        return None
    return IndoorMetric(node_id=node_id, column=column, metric=metric)


def coerce_value(column: str, raw: str) -> float | int | None:
    """Coerce a payload string to the column's type; None on non-numeric.

    ESPHome publishes "nan" when a sensor read fails — that (and any other
    unparseable payload) maps to None so the column is left NULL.
    """
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value != value:  # NaN
        return None
    if column in _INT_COLUMNS:
        return round(value)
    return value
