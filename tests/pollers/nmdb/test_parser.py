"""RED tests for the NMDB / NEST ASCII parser (Phase 13, MU2-06).

Imports parse_nmdb + the NmdbCount dataclass, which Wave 1 (plan 13-03) creates.
Until then these fail at import (expected RED).

Asserts against the pinned NEST OULU fixture (Wave 0): counts are ABSOLUTE
counts/s (yunits=0, NOT a relative scale — Pitfall 3), timestamps are UTC epoch
at the BEGIN of the interval, `null` count tokens become counts_per_sec=None and
count toward the parse-failure threshold, and an empty body raises ValueError.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from observatory.pollers._types import NmdbCount
from observatory.pollers.nmdb.parser import parse_nmdb

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "nmdb" / "sample.txt"


def _fixture_bytes() -> bytes:
    return FIXTURE.read_bytes()


def test_parses_fixture_to_nmdb_counts() -> None:
    rows, meta = parse_nmdb(_fixture_bytes(), station="OULU")
    assert rows, "expected data rows from the pinned fixture"
    assert all(isinstance(r, NmdbCount) for r in rows)
    assert all(r.station == "OULU" for r in rows)
    assert isinstance(meta["fetched_at"], int)
    assert meta["station"] == "OULU"


def test_counts_are_absolute_per_second_not_relative() -> None:
    rows, _meta = parse_nmdb(_fixture_bytes(), station="OULU")
    vals = [r.counts_per_sec for r in rows if r.counts_per_sec is not None]
    assert vals, "expected at least one non-null count"
    # OULU corrected-for-efficiency counts/s sit ~90-110, NOT a 0-100 percent scale
    # nor a 0-1 relative scale; assert the absolute magnitude.
    assert all(v > 50.0 for v in vals)


def test_timestamps_are_utc_epoch_begin_of_interval() -> None:
    rows, _meta = parse_nmdb(_fixture_bytes(), station="OULU")
    first = rows[0]
    # Reconstruct the expected UTC epoch from the first data line of the fixture.
    text = _fixture_bytes().decode("utf-8", "replace")
    line = next(line_ for line_ in text.splitlines() if line_[:4].isdigit() and ";" in line_)
    date_part, _, _ = line.partition(";")
    expected = int(
        datetime.fromisoformat(date_part.strip().replace(" ", "T")).replace(tzinfo=UTC).timestamp()
    )
    assert first.ts == expected


def test_null_token_becomes_none_and_counts_as_failure() -> None:
    rows, meta = parse_nmdb(_fixture_bytes(), station="OULU")
    gaps = [r for r in rows if r.counts_per_sec is None]
    assert gaps, "fixture has trailing null gap rows; expected None counts_per_sec"
    # parser tracks per-row failures (null/gap) for the compute_parse_outcome threshold.
    assert meta["failures"] >= len(gaps)


def test_empty_body_raises_valueerror() -> None:
    with pytest.raises(ValueError):
        parse_nmdb(b"<html><body><pre></pre></body></html>", station="OULU")
