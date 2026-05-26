"""Phase 6 — tests for pagination + serializer helpers (Plan 06-01 RED/GREEN TDD)."""

from __future__ import annotations

import pytest

from observatory.api._pagination import DEFAULT_LIMIT, MAX_LIMIT, resolve_before_ts
from observatory.api._serializers import (
    AGG_VALUES,
    BUCKET_SECONDS,
    BUCKET_SQL_STRFTIME,
    Window,
    resolve_agg,
)


class TestResolveBefore:
    """resolve_before_ts cursor helper."""

    def test_none_returns_default(self) -> None:
        assert resolve_before_ts(None, 1700000000) == 1700000000

    def test_custom_returns_custom(self) -> None:
        assert resolve_before_ts(1699999999, 1700000000) == 1699999999

    def test_default_limit(self) -> None:
        assert DEFAULT_LIMIT == 100

    def test_max_limit(self) -> None:
        assert MAX_LIMIT == 1000


class TestSerializers:
    """AggLiteral + resolve_agg + BUCKET_SECONDS + BUCKET_SQL_STRFTIME + Window."""

    def test_resolve_agg_auto_raw(self) -> None:
        # 3600s = 1h, < 7200s threshold → raw
        assert resolve_agg(3600, "auto") == "raw"

    def test_resolve_agg_auto_minute_boundary(self) -> None:
        # 7200s == 7200; 7200 < 7200 is False → minute
        assert resolve_agg(7200, "auto") == "minute"

    def test_resolve_agg_auto_hour_boundary(self) -> None:
        # 172800s == 2d; 172800 < 172800 is False → hour
        assert resolve_agg(172800, "auto") == "hour"

    def test_resolve_agg_auto_day(self) -> None:
        # 5184000s == 60d; 5184000 < 5184000 is False → day
        assert resolve_agg(5184000, "auto") == "day"

    def test_resolve_agg_non_auto_pass_through(self) -> None:
        # explicit bucket bypasses window logic entirely
        assert resolve_agg(60, "minute") == "minute"

    def test_bucket_seconds_hour(self) -> None:
        assert BUCKET_SECONDS["hour"] == 3600

    def test_bucket_seconds_all(self) -> None:
        assert BUCKET_SECONDS["raw"] == 1
        assert BUCKET_SECONDS["minute"] == 60
        assert BUCKET_SECONDS["hour"] == 3600
        assert BUCKET_SECONDS["day"] == 86400

    def test_bucket_sql_strftime_minute_contains_hm(self) -> None:
        assert "%H:%M" in BUCKET_SQL_STRFTIME["minute"]

    def test_window_attribute_access(self) -> None:
        w = Window(from_ts=100, to_ts=200)
        assert w.from_ts == 100
        assert w.to_ts == 200

    def test_agg_values_tuple(self) -> None:
        assert AGG_VALUES == ("raw", "minute", "hour", "day", "auto")

    def test_resolve_agg_auto_within_raw_range(self) -> None:
        # 1800s = 30min, well within <2h → raw
        assert resolve_agg(1800, "auto") == "raw"

    def test_resolve_agg_auto_within_minute_range(self) -> None:
        # 86400s = 1d, between 2h and 2d → minute
        assert resolve_agg(86400, "auto") == "minute"

    def test_resolve_agg_auto_within_hour_range(self) -> None:
        # 1296000s = 15d, between 2d and 60d → hour
        assert resolve_agg(1296000, "auto") == "hour"

    def test_resolve_agg_auto_large_window_day(self) -> None:
        # 10000000s > 60d → day
        assert resolve_agg(10000000, "auto") == "day"

    @pytest.mark.parametrize("non_auto", ["raw", "minute", "hour", "day"])
    def test_resolve_agg_explicit_all_pass_through(self, non_auto: str) -> None:
        # Any explicit bucket should be returned unchanged regardless of window
        assert resolve_agg(99999999, non_auto) == non_auto  # type: ignore[arg-type]
