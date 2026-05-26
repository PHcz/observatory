"""Pure-function tests for observatory.api._freshness.

Covers per-source thresholds (8 sources x 3 freshness buckets), the worst()
combinator, and the cross_check_poller() override logic that promotes a source
to "down" when poller_runs reports transient_fail OR the poller has gone silent
longer than the down threshold.

These tests have no DB or FastAPI dependencies — pure function in/out.
"""

from __future__ import annotations

import pytest

from observatory.api._freshness import (
    HEALTHY_MULT,
    INTERVALS_SEC,
    STALE_MULT,
    cross_check_poller,
    freshness,
    worst,
)

# ---- freshness() basic boundaries ----


def test_freshness_zero_age_is_healthy() -> None:
    assert freshness(0, 60) == "healthy"


def test_freshness_just_under_healthy_boundary() -> None:
    # 2x boundary at age=120 with interval=60 — just under
    assert freshness(119, 60) == "healthy"


def test_freshness_at_healthy_boundary_promotes_to_stale() -> None:
    # age == HEALTHY_MULT * interval → stale (strict <)
    assert freshness(120, 60) == "stale"


def test_freshness_just_under_stale_boundary() -> None:
    assert freshness(239, 60) == "stale"


def test_freshness_at_stale_boundary_promotes_to_down() -> None:
    assert freshness(240, 60) == "down"


def test_freshness_far_past_stale_is_down() -> None:
    assert freshness(10_000, 60) == "down"


# ---- Per-source x per-bucket truth table ----


@pytest.mark.parametrize(
    ("source", "interval"),
    sorted(INTERVALS_SEC.items()),
)
def test_freshness_at_each_source_boundaries(source: str, interval: int) -> None:
    # Healthy zone
    assert freshness(0, interval) == "healthy"
    assert freshness(HEALTHY_MULT * interval - 1, interval) == "healthy"
    # Stale zone
    assert freshness(HEALTHY_MULT * interval, interval) == "stale"
    assert freshness(STALE_MULT * interval - 1, interval) == "stale"
    # Down zone
    assert freshness(STALE_MULT * interval, interval) == "down"


# ---- worst() combinator ----


def test_worst_healthy_vs_healthy_is_healthy() -> None:
    assert worst("healthy", "healthy") == "healthy"


def test_worst_healthy_vs_stale_is_stale() -> None:
    assert worst("healthy", "stale") == "stale"
    assert worst("stale", "healthy") == "stale"


def test_worst_stale_vs_down_is_down() -> None:
    assert worst("stale", "down") == "down"
    assert worst("down", "stale") == "down"


def test_worst_down_dominates_everything() -> None:
    assert worst("down", "healthy") == "down"
    assert worst("healthy", "down") == "down"


# ---- cross_check_poller() override logic ----

NOW = 1_700_000_000


def test_cross_check_no_poller_history_preserves_event_freshness() -> None:
    assert cross_check_poller("healthy", None, None, NOW, 60) == "healthy"
    assert cross_check_poller("stale", None, None, NOW, 60) == "stale"


def test_cross_check_recent_success_preserves_event_freshness() -> None:
    assert cross_check_poller("healthy", "success", NOW - 30, NOW, 60) == "healthy"


def test_cross_check_recent_partial_preserves_event_freshness() -> None:
    # NOAA-specific: partial is treated as healthy from data-freshness perspective.
    assert cross_check_poller("healthy", "partial", NOW - 30, NOW, 60) == "healthy"


def test_cross_check_recent_transient_fail_promotes_to_down() -> None:
    # Within the down window — override applies.
    assert cross_check_poller("healthy", "transient_fail", NOW - 30, NOW, 60) == "down"


def test_cross_check_old_transient_fail_no_longer_overrides() -> None:
    # Outside down window (4*60=240s) — override does not apply, event freshness wins.
    assert cross_check_poller("healthy", "transient_fail", NOW - 500, NOW, 60) == "healthy"


def test_cross_check_silent_poller_promotes_to_down() -> None:
    # Last poll older than the down threshold (4*60=240s) — poller silent.
    assert cross_check_poller("healthy", "success", NOW - 500, NOW, 60) == "down"


def test_cross_check_parse_fail_does_not_force_down() -> None:
    # parse_fail is a data-quality issue but the poller IS responsive; event-freshness wins.
    assert cross_check_poller("healthy", "parse_fail", NOW - 30, NOW, 60) == "healthy"
