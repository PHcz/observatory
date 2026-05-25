"""USGS GeoJSON parser tests — closes POLL-01 parse contract + checker WARNING 1.

The parser is contractually defined to return ``(events, parse_failures)``:
good items flow through, per-item failures are counted + WARNING-logged
with a truncated raw dump, structural failures still raise.
"""

from __future__ import annotations

import json
from collections.abc import Callable

import pytest
import structlog
from structlog.testing import capture_logs

from observatory.pollers._types import EarthquakeEvent
from observatory.pollers.usgs.parser import parse_usgs


def _make_feature(
    *,
    fid: str = "us_test_001",
    mag: float = 4.9,
    time_ms: int = 1779725577904,
    coords: list[float] | str | None = None,
    place: str | None = "Somewhere",
    drop_mag: bool = False,
) -> dict:
    if coords is None:
        coords = [-25.7657, -57.9499, 131.676]
    props: dict = {"time": time_ms}
    if not drop_mag:
        props["mag"] = mag
    if place is not None:
        props["place"] = place
    return {
        "type": "Feature",
        "id": fid,
        "properties": props,
        "geometry": {"type": "Point", "coordinates": coords},
    }


def _wrap(features: list[dict]) -> bytes:
    return json.dumps({"type": "FeatureCollection", "features": features}).encode()


# ---------- Real fixture ----------


def test_parse_real_fixture(load_eq_fixture: Callable[[str], bytes]) -> None:
    body = load_eq_fixture("usgs/sample_4_5_day.json")
    events, failures = parse_usgs(body)
    assert len(events) >= 1
    assert failures == 0
    for ev in events:
        assert isinstance(ev, EarthquakeEvent)
        assert ev.source == "usgs"
        assert isinstance(ev.external_id, str) and ev.external_id
        assert isinstance(ev.ts, int) and ev.ts > 0
        assert isinstance(ev.magnitude, float)
        assert -90.0 <= ev.latitude <= 90.0
        assert -180.0 <= ev.longitude <= 180.0
        assert ev.depth_km is None or isinstance(ev.depth_km, float)


def test_parse_returns_unique_external_ids_on_real_fixture(
    load_eq_fixture: Callable[[str], bytes],
) -> None:
    body = load_eq_fixture("usgs/sample_4_5_day.json")
    events, _ = parse_usgs(body)
    ids = [ev.external_id for ev in events]
    assert len(set(ids)) == len(ids)


def test_parse_real_fixture_ts_in_2026_range(
    load_eq_fixture: Callable[[str], bytes],
) -> None:
    body = load_eq_fixture("usgs/sample_4_5_day.json")
    events, _ = parse_usgs(body)
    # 2026-01-01 .. 2027-01-01 in unix seconds
    lo = 1767225600
    hi = 1798761600
    for ev in events:
        assert lo <= ev.ts <= hi, f"ts {ev.ts} for {ev.external_id} not in 2026"


# ---------- Field-by-field synthetic checks ----------


def test_parse_time_is_ms_epoch_not_iso() -> None:
    body = _wrap([_make_feature(time_ms=1779725577904)])
    events, failures = parse_usgs(body)
    assert failures == 0
    assert events[0].ts == 1779725577


def test_parse_uses_feature_id_as_external_id() -> None:
    body = _wrap([_make_feature(fid="us_test_123")])
    events, _ = parse_usgs(body)
    assert events[0].external_id == "us_test_123"


def test_parse_coordinates_are_lon_lat_depth() -> None:
    body = _wrap([_make_feature(coords=[-25.7657, -57.9499, 131.676])])
    events, _ = parse_usgs(body)
    assert events[0].longitude == -25.7657
    assert events[0].latitude == -57.9499
    assert events[0].depth_km == 131.676


def test_parse_handles_missing_depth() -> None:
    body = _wrap([_make_feature(coords=[10.0, 20.0])])
    events, failures = parse_usgs(body)
    assert failures == 0
    assert events[0].depth_km is None
    assert events[0].longitude == 10.0
    assert events[0].latitude == 20.0


def test_parse_handles_missing_place() -> None:
    body = _wrap([_make_feature(place=None)])
    events, _ = parse_usgs(body)
    assert events[0].place is None


def test_parse_empty_features() -> None:
    body = _wrap([])
    events, failures = parse_usgs(body)
    assert events == []
    assert failures == 0


# ---------- Partial-parse cases (CONTEXT-locked, closes checker WARNING 1) ----------


def test_parse_partial_failure_increments_counter() -> None:
    features = [_make_feature(fid=f"good_{i}") for i in range(8)]
    features += [
        _make_feature(fid="bad_1", drop_mag=True),
        _make_feature(fid="bad_2", drop_mag=True),
    ]
    body = _wrap(features)
    events, failures = parse_usgs(body)
    assert len(events) == 8
    assert failures == 2


def test_parse_partial_failure_logs_warning_with_truncated_raw() -> None:
    features = [
        _make_feature(fid="bad_a", drop_mag=True),
        _make_feature(fid="bad_b", drop_mag=True),
    ]
    body = _wrap(features)
    # capture_logs needs the structlog logger to be reconfigured; conftest
    # already calls configure_logging, but capture_logs installs its own
    # processor stack for the duration of the with-block.
    with capture_logs() as logs:
        events, failures = parse_usgs(body)
    assert events == []
    assert failures == 2
    warnings = [e for e in logs if e.get("log_level") == "warning"]
    assert len(warnings) == 2
    for entry in warnings:
        assert "raw" in entry
        assert isinstance(entry["raw"], str)
        assert len(entry["raw"]) <= 200


def test_parse_per_item_typeerror_caught() -> None:
    # coordinates as a string triggers TypeError on coords[2] / coords[1] indexing-of-string
    # or ValueError on float() conversion — both are caught.
    body = _wrap([_make_feature(coords="not-a-list")])  # type: ignore[arg-type]
    events, failures = parse_usgs(body)
    assert events == []
    assert failures == 1


# ---------- Structural failures still raise ----------


def test_parse_not_json_raises() -> None:
    with pytest.raises(json.JSONDecodeError):
        parse_usgs(b"not json at all")


# ---------- Smoke: structlog import works (defensive against test ordering) ----------


def test_structlog_get_logger_works() -> None:
    log = structlog.get_logger("test")
    log.info("smoke")
