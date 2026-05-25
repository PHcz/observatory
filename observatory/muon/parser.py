"""Pure-function PicoMuon CSV line parser. No I/O, no logging — testable with strings.

Protocol:
    7-field (upstream UKRAA):  Position,Count,ADC,PicoTime,DeadTime,PicoTemp,PicoPres
    8-field (observed):        ..., PicoPres, DeviceID  (DeviceID = trailing static ID)

Both variants are accepted. The 8th field is a static device identifier
(observed value `56-597-118` on PID 000a, serial E663589863348027 — likely a
firmware version triple). It is preserved on the parsed event as
`device_id` (None for 7-field firmware) so the reader can log it once at
startup as device metadata. It is NOT written to muon_events — the schema
stays lean per 02-CONTEXT.md "Implementation Decisions → Serial parsing".

Lines are newline-terminated, transmitted at 115200 8N1 over USB CDC-ACM.
The firmware emits `\\n\\n` between events; the reader handles the blank-line
case by stripping and skipping. BMP280 temperature and pressure are present
on EVERY event line (not periodic), so each parsed MuonEvent always carries
detector_temp_c and detector_pressure_hpa values — satisfying MUON-03's
pressure-correction contract.

Field-to-column mapping (matches migrations/0001_initial_schema.sql.muon_events):
    Position  'T'|'B'|'C'  -> coincidence (1 iff 'C', else 0)
    Count     int          -> dropped (debug only)
    ADC       int 0..1023  -> amplitude
    PicoTime  int/float    -> dropped (Pi wall clock owns ts)
    DeadTime  int/float    -> dropped (debug only)
    PicoTemp  float (°C)   -> detector_temp_c
    PicoPres  float (hPa)  -> detector_pressure_hpa
    DeviceID  str (opt.)   -> MuonEvent.device_id (not persisted; logged once)

Deviation history:
    2026-05-25 — Real device emits 8 fields, not the 7 documented in upstream
    UKRAA scripts. See .planning/phases/02-muon-detector/02-01-CAPTURE-NOTES.md
    "Protocol deviation" section. Parser relaxed to accept both.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

VALID_FIELD_COUNTS: Final[frozenset[int]] = frozenset({7, 8})
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
    device_id: str | None = None  # 8th field if firmware emits it; None for 7-field firmware

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
    if len(fields) not in VALID_FIELD_COUNTS:
        raise ParseError(f"expected 7 or 8 fields, got {len(fields)}: {text!r}")

    position = fields[0]
    adc = fields[2]
    picotemp = fields[5]
    picopres = fields[6]
    device_id = fields[7] if len(fields) == 8 else None

    if position not in VALID_POSITIONS:
        raise ParseError(f"invalid position {position!r}, expected one of T/B/C")

    try:
        return MuonEvent(
            position=position,
            amplitude=int(adc),
            detector_temp_c=float(picotemp),
            detector_pressure_hpa=float(picopres),
            device_id=device_id,
        )
    except ValueError as exc:
        raise ParseError(f"numeric parse failed: {text!r}") from exc
