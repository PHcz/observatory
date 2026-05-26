"""Fixtures for Blitzortung tests — frame loader for the length-prefixed bin."""

from __future__ import annotations

import struct
from collections.abc import Callable
from pathlib import Path

import pytest


def _parse_length_prefixed(buf: bytes) -> list[bytes]:
    """Split a length-prefixed (>I) frame stream into individual frames."""
    out: list[bytes] = []
    i = 0
    n = len(buf)
    while i + 4 <= n:
        (length,) = struct.unpack_from(">I", buf, i)
        i += 4
        if length == 0 or i + length > n:
            break
        out.append(buf[i : i + length])
        i += length
    return out


@pytest.fixture
def load_frames(fixtures_dir: Path) -> Callable[[], list[bytes]]:
    """Return the list of captured Blitzortung WS frames from the pinned bin.

    Pre-port-probe the fixture is a 17-byte ASCII placeholder; in that case
    we return an empty list and the consumer should ``pytest.skip``.
    """
    path = fixtures_dir / "blitzortung" / "sample_frames.bin"

    def _load() -> list[bytes]:
        if not path.exists():
            return []
        raw = path.read_bytes()
        # Length-prefixed payload only — placeholder is shorter than one frame.
        if len(raw) < 8:
            return []
        frames = _parse_length_prefixed(raw)
        return frames

    return _load
