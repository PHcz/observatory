"""Parser tests for EMSC FDSNWS GeoJSON.

Covers CONTEXT-locked per-item resilience: bad items count as failures
without propagating, good items flow. Real fixture is the pinned 2026-05-25
capture from seismicportal.eu.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import cast

import pytest
import structlog
from structlog.testing import capture_logs

from observatory.pollers.emsc.parser import parse_emsc


def _make_feature(
    *,
    feat_id: str = "20260525_0000999",
    unid: str = "20260525_0000999",
    time_str: str = "2026-05-25T19:49:24.0Z",
    mag: float = 3.0,
    depth: float | None = 17.0,
    lat: float = -8.14,
    lon: float = 117.79,
    flynn: str | None = "TEST REGION",
    coords: list[float] | None = None,
) -> dict[str, object]:
    if coords is None:
        coords = [lon, lat, -(depth or 0.0)]
    return {
        "type": "Feature",
        "id": feat_id,
        "geometry": {"type": "Point", "coordinates": coords},
        "properties": {
            "source_id": "x",
            "lastupdate": "2026-05-25T19:56:27.770145Z",
            "time": time_str,
            "flynn_region": flynn,
            "lat": lat,
            "lon": lon,
            "depth": depth,
            "mag": mag,
            "unid": unid,
        },
    }


def _wrap(features: list[dict[str, object]]) -> bytes:
    return json.dumps({"type": "FeatureCollection", "features": features}).encode("utf-8")


def test_parse_real_fixture(load_eq_fixture: Callable[[str], bytes]) -> None:
    body = load_eq_fixture("emsc/sample_pastday.json")
    events, failures = parse_emsc(body)
    assert len(events) >= 1
    assert failures == 0
    for ev in events:
        assert ev.source == "emsc"
        assert isinstance(ev.external_id, str) and ev.external_id
        assert isinstance(ev.ts, int) and ev.ts > 0
        assert isinstance(ev.magnitude, float)
        assert -90.0 <= ev.latitude <= 90.0
        assert -180.0 <= ev.longitude <= 180.0


def test_parse_returns_tuple_signature() -> None:
    """parse_emsc must return tuple[list, int] for compute_parse_outcome wiring."""
    result = parse_emsc(_wrap([]))
    assert isinstance(result, tuple)
    assert len(result) == 2
    events, failures = result
    assert events == []
    assert failures == 0


def test_parse_uses_unid_not_feature_id() -> None:
    feat = _make_feature(feat_id="outer-id", unid="inner-id")
    events, failures = parse_emsc(_wrap([feat]))
    assert failures == 0
    assert events[0].external_id == "inner-id"


def test_parse_time_via_parse_ts() -> None:
    expected = int(datetime(2026, 5, 25, 19, 49, 24, tzinfo=UTC).timestamp())
    feat = _make_feature(time_str="2026-05-25T19:49:24.0Z")
    events, failures = parse_emsc(_wrap([feat]))
    assert failures == 0
    assert events[0].ts == expected


def test_parse_handles_microsecond_precision() -> None:
    expected = int(datetime(2026, 5, 25, 19, 49, 24, tzinfo=UTC).timestamp())
    feat = _make_feature(time_str="2026-05-25T19:49:24.123456Z")
    events, failures = parse_emsc(_wrap([feat]))
    assert failures == 0
    assert events[0].ts == expected


def test_parse_naive_time_counted_as_failure_not_raised() -> None:
    """ParseError from parse_ts on naive time must be caught per-item, not propagate."""
    good = _make_feature(unid="good")
    bad = _make_feature(unid="bad", time_str="2026-05-25T19:49:24")  # naive
    events, failures = parse_emsc(_wrap([good, bad]))
    assert len(events) == 1
    assert failures == 1
    assert events[0].external_id == "good"


def test_parse_uses_props_lat_lon_not_coordinates() -> None:
    """props.lat/lon is canonical; geometry.coordinates is ignored for lat/lon."""
    feat = _make_feature(lat=10.0, lon=20.0, coords=[99.0, 99.0, -5.0])
    events, failures = parse_emsc(_wrap([feat]))
    assert failures == 0
    assert events[0].latitude == 10.0
    assert events[0].longitude == 20.0


def test_parse_uses_props_depth() -> None:
    feat = _make_feature(depth=17.0)
    events, failures = parse_emsc(_wrap([feat]))
    assert failures == 0
    assert events[0].depth_km == 17.0


def test_parse_handles_null_depth() -> None:
    feat = _make_feature(depth=None)
    events, failures = parse_emsc(_wrap([feat]))
    assert failures == 0
    assert events[0].depth_km is None


def test_parse_place_from_flynn_region() -> None:
    feat = _make_feature(flynn="SUMBAWA REGION, INDONESIA")
    events, failures = parse_emsc(_wrap([feat]))
    assert failures == 0
    assert events[0].place == "SUMBAWA REGION, INDONESIA"


def test_parse_empty_features() -> None:
    body = json.dumps({"type": "FeatureCollection", "features": []}).encode("utf-8")
    events, failures = parse_emsc(body)
    assert events == []
    assert failures == 0


def test_parse_structural_error_raises_for_main_to_catch() -> None:
    """json.JSONDecodeError on whole-payload bad bytes still propagates (structural)."""
    with pytest.raises(json.JSONDecodeError):
        parse_emsc(b"not json at all")


def test_parse_partial_failure_increments_counter() -> None:
    """8 good + 2 missing unid -> (8, 2). Per-item KeyError caught, not raised."""
    good = [_make_feature(unid=f"g{i}") for i in range(8)]
    bad: list[dict[str, object]] = []
    for _ in range(2):
        f = _make_feature()
        props = cast(dict[str, object], f["properties"])
        del props["unid"]
        bad.append(f)
    events, failures = parse_emsc(_wrap(good + bad))
    assert len(events) == 8
    assert failures == 2


def test_parse_partial_failure_logs_warning_with_truncated_raw() -> None:
    """Each per-item failure emits a WARNING with truncated raw field (≤200 chars)."""
    bad: list[dict[str, object]] = []
    for _ in range(2):
        f = _make_feature()
        props = cast(dict[str, object], f["properties"])
        del props["unid"]
        bad.append(f)
    structlog.configure(
        processors=[structlog.testing.LogCapture()],
        wrapper_class=structlog.BoundLogger,
    )
    with capture_logs() as logs:
        events, failures = parse_emsc(_wrap(bad))
    assert events == []
    assert failures == 2
    warnings = [e for e in logs if e.get("log_level") == "warning"]
    assert len(warnings) == 2
    for w in warnings:
        assert "raw" in w
        assert isinstance(w["raw"], str)
        assert len(w["raw"]) <= 200


def test_parse_per_item_typeerror_caught() -> None:
    """A feature with a non-numeric mag string triggers ValueError on float() — counted."""
    good = _make_feature(unid="g0")
    bad = _make_feature(unid="b0")
    bad_props = cast(dict[str, object], bad["properties"])
    bad_props["mag"] = "not-a-number"
    events, failures = parse_emsc(_wrap([good, bad]))
    assert len(events) == 1
    assert failures == 1
