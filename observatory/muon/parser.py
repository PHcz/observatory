"""Pure-function PicoMuon CSV line parser. No I/O, no logging — testable with strings.

Protocol (HIGH confidence, confirmed from upstream UKRAA firmware source):
    Position,Count,ADC,PicoTime,DeadTime,PicoTemp,PicoPres

7 comma-separated fields per event, newline-terminated, transmitted at 115200 8N1
over USB CDC-ACM. BMP280 temperature and pressure are present on EVERY event line
(not periodic), so each parsed MuonEvent always carries detector_temp_c and
detector_pressure_hpa values — satisfying MUON-03's pressure-correction contract.

Field-to-column mapping (matches migrations/0001_initial_schema.sql.muon_events):
    Position  'T'|'B'|'C'  -> coincidence (1 iff 'C', else 0)
    Count     int          -> dropped (debug only)
    ADC       int 0..1023  -> amplitude
    PicoTime  int/float    -> dropped (Pi wall clock owns ts)
    DeadTime  int/float    -> dropped (debug only)
    PicoTemp  float (°C)   -> detector_temp_c
    PicoPres  float (hPa)  -> detector_pressure_hpa
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

NUM_FIELDS: Final[int] = 7
VALID_POSITIONS: Final[frozenset[str]] = frozenset({"T", "B", "C"})


class ParseError(ValueError):
    """Raised when a line cannot be parsed as a PicoMuon event."""


@dataclass(frozen=True, slots=True)
class MuonEvent:
    """One parsed PicoMuon event. Immutable.

    Maps directly to a muon_events row (ts is stamped by the reader, not the parser).
    """

    position: str  # 'T' | 'B' | 'C'
    amplitude: int  # ADC value 0..1023
    detector_temp_c: float
    detector_pressure_hpa: float

    @property
    def coincidence(self) -> int:
        """1 if both SiPMs fired (Position='C'), else 0."""
        return 1 if self.position == "C" else 0


def parse_line(raw: bytes | str) -> MuonEvent:
    """Parse one PicoMuon CSV line into a MuonEvent.

    Accepts bytes (UTF-8) or str. Strips trailing whitespace/newline before
    splitting. Raises ParseError on any shape or numeric-conversion failure;
    never returns partial data.
    """
    if isinstance(raw, bytes):
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ParseError(f"undecodable bytes: {raw!r}") from exc
    else:
        text = raw

    stripped = text.strip()
    if not stripped:
        raise ParseError("empty line")

    fields = stripped.split(",")
    if len(fields) != NUM_FIELDS:
        raise ParseError(f"expected {NUM_FIELDS} fields, got {len(fields)}: {text!r}")

    position, _count, adc, _picotime, _deadtime, picotemp, picopres = fields
    if position not in VALID_POSITIONS:
        raise ParseError(f"invalid position {position!r}, expected one of T/B/C")

    try:
        return MuonEvent(
            position=position,
            amplitude=int(adc),
            detector_temp_c=float(picotemp),
            detector_pressure_hpa=float(picopres),
        )
    except ValueError as exc:
        raise ParseError(f"numeric parse failed: {text!r}") from exc
