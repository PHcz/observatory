"""POLL-07 contract: parse_ts strict ISO 8601 -> UTC unix epoch."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from observatory.pollers._parse_ts import ParseError, parse_ts

EXPECTED = int(datetime(2026, 5, 25, 14, 30, 0, tzinfo=UTC).timestamp())


@pytest.mark.parametrize(
    "raw",
    [
        "2026-05-25T14:30:00Z",
        "2026-05-25T14:30:00+00:00",
        "2026-05-25T14:30:00.123456Z",
        "2026-05-25T15:30:00+01:00",
    ],
)
def test_parse_ts_valid_iso_variants(raw: str) -> None:
    assert parse_ts(raw) == EXPECTED


@pytest.mark.parametrize(
    "raw",
    [
        "2026-05-25T14:30:00",  # naive
        "",
        "not-a-date",
        "2026-05-25",
    ],
)
def test_parse_ts_rejects_invalid(raw: str) -> None:
    with pytest.raises(ParseError):
        parse_ts(raw)


def test_parse_ts_rejects_none() -> None:
    with pytest.raises(ParseError):
        parse_ts(None)  # type: ignore[arg-type]


def test_parse_error_is_value_error_subclass() -> None:
    assert issubclass(ParseError, ValueError)
