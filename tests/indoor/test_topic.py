"""Phase 14 INDOOR-03: pure topic/payload parsing for the indoor subscriber."""

from __future__ import annotations

import pytest

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


# --- Implausible values (security audit 2026-10-20, M4) ---------------------
# coerce_value("co2_ppm", "inf") used to raise OverflowError from round(); the
# subscriber caught only MQTT errors, so one bad frame killed indoor ingestion
# until obs-api restarted. Non-finite or physically impossible values now leave
# the column NULL, like ESPHome's "nan".


@pytest.mark.parametrize(
    ("column", "raw"),
    [("co2_ppm", "inf"), ("co2_ppm", "-inf"), ("temp_c", "inf"), ("temp_c", "1e309")],
)
def test_non_finite_values_become_none(column: str, raw: str) -> None:
    assert coerce_value(column, raw) is None


@pytest.mark.parametrize(
    ("column", "raw"),
    [("co2_ppm", "1e12"), ("temp_c", "500"), ("humidity_pct", "250"), ("pressure_hpa", "5")],
)
def test_physically_impossible_values_become_none(column: str, raw: str) -> None:
    assert coerce_value(column, raw) is None


@pytest.mark.parametrize(
    ("column", "raw", "expected"),
    [  # real extremes from the live database, 2026-10-20
        ("co2_ppm", "4791", 4791),
        ("co2_ppm", "0", 0),
        ("temp_c", "37.6", 37.6),
        ("humidity_pct", "100.0", 100.0),
        ("pressure_hpa", "1030.9", 1030.9),
    ],
)
def test_real_extremes_are_kept(column: str, raw: str, expected: float) -> None:
    assert coerce_value(column, raw) == expected
