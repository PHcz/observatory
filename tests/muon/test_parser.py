"""Unit tests for observatory.muon.parser.

Tests the PicoMuon CSV line parser against:
- Hand-crafted valid events covering all 3 Positions (T, B, C)
- Hand-crafted malformed lines for each ParseError path
- Fixture files (sample_malformed.txt, sample_partial_first_line.txt) committed in 02-00
- The real captured sample.csv (committed by 02-01) when present, otherwise skipped

The parser is pure: takes bytes|str, returns MuonEvent, or raises ParseError.
No I/O, no logging, no clocks — testable with strings only.

Wire protocol (RESEARCH.md, HIGH confidence, quoted verbatim from upstream UKRAA source):
    Position,Count,ADC,PicoTime,DeadTime,PicoTemp,PicoPres
"""

from __future__ import annotations

from pathlib import Path

import pytest

from observatory.muon.parser import MuonEvent, ParseError, parse_line

# --------------------------------------------------------------------------- #
# Valid event parsing                                                          #
# --------------------------------------------------------------------------- #


def test_parse_valid_coincidence_event() -> None:
    ev = parse_line("C,1234,512,5000123,42,21.3,1013.25")
    assert isinstance(ev, MuonEvent)
    assert ev.position == "C"
    assert ev.amplitude == 512
    assert ev.detector_temp_c == 21.3
    assert ev.detector_pressure_hpa == 1013.25
    assert ev.coincidence == 1


def test_parse_valid_top_event() -> None:
    ev = parse_line("T,1235,256,5000456,42,20.1,1012.50")
    assert ev.position == "T"
    assert ev.amplitude == 256
    assert ev.detector_temp_c == 20.1
    assert ev.detector_pressure_hpa == 1012.50
    assert ev.coincidence == 0


def test_parse_valid_bottom_event() -> None:
    ev = parse_line("B,1236,300,5000789,42,20.2,1011.00")
    assert ev.position == "B"
    assert ev.amplitude == 300
    assert ev.detector_temp_c == 20.2
    assert ev.detector_pressure_hpa == 1011.00
    assert ev.coincidence == 0


def test_parse_accepts_bytes_input() -> None:
    ev = parse_line(b"C,1,2,3,4,5.0,6.0\n")
    assert ev.position == "C"
    assert ev.amplitude == 2
    assert ev.detector_temp_c == 5.0
    assert ev.detector_pressure_hpa == 6.0


def test_parse_strips_trailing_newline_and_cr() -> None:
    ev_lf = parse_line("C,1,2,3,4,5.0,6.0\n")
    ev_crlf = parse_line("C,1,2,3,4,5.0,6.0\r\n")
    assert ev_lf == ev_crlf


# --------------------------------------------------------------------------- #
# Malformed input — each path raises ParseError                                #
# --------------------------------------------------------------------------- #


def test_parse_wrong_field_count_raises() -> None:
    with pytest.raises(ParseError) as excinfo:
        parse_line("C,1237,512,5001000,42")
    # Message should mention expected field count
    assert "7" in str(excinfo.value) or "field" in str(excinfo.value).lower()


def test_parse_too_many_fields_raises() -> None:
    with pytest.raises(ParseError):
        parse_line("C,1,2,3,4,5,6,7,8")


def test_parse_invalid_position_raises() -> None:
    with pytest.raises(ParseError) as excinfo:
        parse_line("X,1235,256,5000456,42,21.3,1013.25")
    # Message should mention the invalid position
    assert "X" in str(excinfo.value) or "position" in str(excinfo.value).lower()


def test_parse_non_numeric_adc_raises() -> None:
    with pytest.raises(ParseError):
        parse_line("C,1236,not_a_number,5000789,42,21.3,1013.25")


def test_parse_non_numeric_temp_raises() -> None:
    with pytest.raises(ParseError):
        parse_line("C,1,512,3,4,not_a_temp,1013.25")


def test_parse_startup_banner_raises() -> None:
    with pytest.raises(ParseError):
        parse_line("--- PicoMuon v0.9 startup banner ---")


def test_parse_empty_string_raises() -> None:
    with pytest.raises(ParseError):
        parse_line("")


# --------------------------------------------------------------------------- #
# Fixture-driven tests                                                         #
# --------------------------------------------------------------------------- #


def test_parse_fixture_malformed_each_line(load_fixture) -> None:
    text = load_fixture("sample_malformed.txt")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    # First line is the only valid event in this fixture
    ev = parse_line(lines[0])
    assert ev.position == "C"
    assert ev.amplitude == 512
    # Remaining four lines must each raise ParseError
    for bad in lines[1:]:
        with pytest.raises(ParseError):
            parse_line(bad)


def test_parse_fixture_partial_first_line(load_fixture) -> None:
    text = load_fixture("sample_partial_first_line.txt")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    # First line is a truncated head-of-stream fragment — must raise
    with pytest.raises(ParseError):
        parse_line(lines[0])
    # Subsequent two lines parse cleanly
    ev1 = parse_line(lines[1])
    ev2 = parse_line(lines[2])
    assert ev1.position == "T"
    assert ev2.position == "B"


def test_parse_real_sample_when_present() -> None:
    real = Path(__file__).resolve().parents[1] / "fixtures" / "muon" / "sample.csv"
    if not real.exists():
        pytest.skip("real sample.csv not yet captured by plan 02-01")
    lines = [ln for ln in real.read_text().splitlines() if ln.strip()]
    successes: list[MuonEvent] = []
    for ln in lines:
        try:
            successes.append(parse_line(ln))
        except ParseError:
            pass
    assert len(successes) >= 0.9 * len(lines), f"only {len(successes)}/{len(lines)} parsed (<90%)"
    # Every successfully-parsed event carries BMP280 fields (MUON-03 contract)
    for ev in successes:
        assert ev.detector_temp_c is not None
        assert ev.detector_pressure_hpa is not None
    # Real PID-000a firmware emits the 8-field variant; device_id should be set
    # and identical across the whole capture session (the actual value identifies
    # a specific device — fixture sanitized to "XX-XXX-XXX" for public repo).
    device_ids = {ev.device_id for ev in successes}
    assert len(device_ids) == 1, f"expected single static device_id, got {device_ids}"
    assert next(iter(device_ids)) is not None, "device_id required on 8-field firmware"


# --------------------------------------------------------------------------- #
# 8-field protocol variant (deviation captured 2026-05-25, see 02-01 notes)   #
# --------------------------------------------------------------------------- #


def test_parse_8_field_variant_extracts_device_id() -> None:
    """PID-000a firmware emits Position,Count,ADC,PicoTime,DeadTime,PicoTemp,PicoPres,DeviceID."""
    line = "T,619,84,395652,349,27.8,1031.2,XX-XXX-XXX"
    ev = parse_line(line)
    assert ev.position == "T"
    assert ev.amplitude == 84
    assert ev.detector_temp_c == 27.8
    assert ev.detector_pressure_hpa == 1031.2
    assert ev.device_id == "XX-XXX-XXX"
    assert ev.coincidence == 0


def test_parse_7_field_variant_has_no_device_id() -> None:
    """Upstream UKRAA firmware (7 fields) still parses; device_id is None."""
    line = "C,42,512,123456,789,22.5,1013.25"
    ev = parse_line(line)
    assert ev.position == "C"
    assert ev.amplitude == 512
    assert ev.device_id is None
    assert ev.coincidence == 1


def test_parse_rejects_neither_7_nor_8_fields() -> None:
    """6 or 9 fields must raise — only 7 and 8 are valid PicoMuon shapes."""
    with pytest.raises(ParseError, match="expected 7 or 8 fields"):
        parse_line("T,1,2,3,4,5")  # 6
    with pytest.raises(ParseError, match="expected 7 or 8 fields"):
        parse_line("T,1,2,3,4,5,6,7,8")  # 9


# --------------------------------------------------------------------------- #
# MuonEvent dataclass invariants                                               #
# --------------------------------------------------------------------------- #


def test_muon_event_is_frozen() -> None:
    from dataclasses import FrozenInstanceError

    ev = parse_line("C,1,2,3,4,5.0,6.0")
    # frozen=True dataclasses raise FrozenInstanceError on attribute assignment.
    # FrozenInstanceError subclasses AttributeError per the stdlib docs.
    with pytest.raises((FrozenInstanceError, AttributeError)):
        ev.position = "T"  # type: ignore[misc]
