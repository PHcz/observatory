"""RED tests for the %-of-baseline pure function (Phase 13, MU2-06).

Imports pct_of_baseline from observatory.api._baseline, which Wave 3 (plan 13-04)
creates -> import fails RED until then.

Contract (research §%-of-baseline): baseline = rolling median over the window
(robust to Poisson spikes + gaps); pct = 100 * value / baseline. Gaps (None) pass
through as None; an empty list returns an empty list. The median is computed over
non-null values only.
"""

from __future__ import annotations

from observatory.api._baseline import pct_of_baseline


def test_empty_list_returns_empty() -> None:
    assert pct_of_baseline([]) == []


def test_constant_series_is_100_pct() -> None:
    out = pct_of_baseline([100.0, 100.0, 100.0, 100.0])
    assert all(v is not None and abs(v - 100.0) < 1e-9 for v in out)


def test_median_normalisation() -> None:
    # median([90, 100, 110]) = 100 -> pct = value / 100 * 100 = value.
    out = pct_of_baseline([90.0, 100.0, 110.0])
    assert out[0] is not None and abs(out[0] - 90.0) < 1e-9
    assert out[1] is not None and abs(out[1] - 100.0) < 1e-9
    assert out[2] is not None and abs(out[2] - 110.0) < 1e-9


def test_gaps_pass_through_as_none() -> None:
    out = pct_of_baseline([100.0, None, 100.0])
    assert out[1] is None
    # baseline computed over non-null values; the present values normalise to 100.
    assert out[0] is not None and abs(out[0] - 100.0) < 1e-9
    assert out[2] is not None and abs(out[2] - 100.0) < 1e-9


def test_all_none_returns_all_none() -> None:
    out = pct_of_baseline([None, None, None])
    assert out == [None, None, None]
