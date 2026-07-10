"""Phase 14 INDOOR-03: pure topic/payload parsing for the indoor subscriber."""

from __future__ import annotations

from observatory.indoor.topic import IndoorMetric, coerce_value, parse_metric_topic


class TestParseMetricTopic:
    def test_valid_co2_topic(self) -> None:
        r = parse_metric_topic("indoor/living-room/sensor/co2/state")
        assert r == IndoorMetric(node_id="living-room", column="co2_ppm", metric="co2")

    def test_all_current_metrics_map(self) -> None:
        cases = {
            "temperature": "temp_c",
            "humidity": "humidity_pct",
            "pressure": "pressure_hpa",
            "co2": "co2_ppm",
        }
        for metric, column in cases.items():
            r = parse_metric_topic(f"indoor/bedroom/sensor/{metric}/state")
            assert r is not None and r.node_id == "bedroom" and r.column == column

    def test_status_topic_ignored(self) -> None:
        assert parse_metric_topic("indoor/living-room/status") is None

    def test_debug_topic_ignored(self) -> None:
        assert parse_metric_topic("indoor/living-room/debug") is None

    def test_unknown_metric_ignored(self) -> None:
        assert parse_metric_topic("indoor/living-room/sensor/tvoc/state") is None

    def test_wrong_prefix_ignored(self) -> None:
        assert parse_metric_topic("enviro/observatory-weather/sensor/co2/state") is None

    def test_malformed_topic_ignored(self) -> None:
        assert parse_metric_topic("indoor/living-room/sensor/co2") is None  # missing /state
        assert parse_metric_topic("indoor//sensor/co2/state") is None  # empty node


class TestCoerceValue:
    def test_co2_is_integer(self) -> None:
        v = coerce_value("co2_ppm", "822")
        assert v == 822 and isinstance(v, int)

    def test_co2_rounds_float_payload(self) -> None:
        assert coerce_value("co2_ppm", "821.6") == 822

    def test_temperature_is_float(self) -> None:
        v = coerce_value("temp_c", "21.4")
        assert v == 21.4 and isinstance(v, float)

    def test_nan_becomes_none(self) -> None:
        assert coerce_value("co2_ppm", "nan") is None

    def test_non_numeric_becomes_none(self) -> None:
        assert coerce_value("temp_c", "online") is None
