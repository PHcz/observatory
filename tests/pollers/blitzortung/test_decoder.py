"""LZW decoder tests against the pinned real-frame fixture.

The decoder reverses Blitzortung's obfuscation per the gkbrk +
SimonSchick community writeups (RESEARCH §"Pattern 3"). It is a pure
function: bytes in, JSON bytes out.

Fixture is produced by ``tests/pollers/blitzortung/test_port_probe.py``
(network-marked). If the fixture is the 17-byte placeholder these tests
``pytest.skip`` rather than fail — the operator hasn't run the probe yet.
"""

from __future__ import annotations

import json
from collections.abc import Callable

import pytest


def test_decode_first_frame_yields_valid_json(load_frames: Callable[[], list[bytes]]) -> None:
    from observatory.pollers.blitzortung.decoder import decode

    frames = load_frames()
    if not frames:
        pytest.skip("sample_frames.bin is the placeholder; run the network probe to refresh.")
    decoded = decode(frames[0])
    payload = json.loads(decoded)
    assert {"time", "lat", "lon"}.issubset(payload.keys())


def test_decode_all_frames_have_expected_shape(
    load_frames: Callable[[], list[bytes]],
) -> None:
    from observatory.pollers.blitzortung.decoder import decode

    frames = load_frames()
    if not frames:
        pytest.skip("sample_frames.bin is the placeholder; run the network probe to refresh.")
    for i, raw in enumerate(frames):
        decoded = decode(raw)
        payload = json.loads(decoded)
        assert isinstance(payload["time"], int), f"frame {i}: time not int"
        assert isinstance(payload["lat"], (int, float)), f"frame {i}: lat not numeric"
        assert isinstance(payload["lon"], (int, float)), f"frame {i}: lon not numeric"
        # time is nanoseconds since epoch (gkbrk + community confirm)
        assert payload["time"] > 1_000_000_000_000_000_000, (
            f"frame {i}: time looks too small to be ns-epoch"
        )


def test_decode_is_deterministic(load_frames: Callable[[], list[bytes]]) -> None:
    from observatory.pollers.blitzortung.decoder import decode

    frames = load_frames()
    if not frames:
        pytest.skip("sample_frames.bin is the placeholder; run the network probe to refresh.")
    a = decode(frames[0])
    b = decode(frames[0])
    assert a == b


def test_decode_returns_bytes(load_frames: Callable[[], list[bytes]]) -> None:
    from observatory.pollers.blitzortung.decoder import decode

    frames = load_frames()
    if not frames:
        pytest.skip("sample_frames.bin is the placeholder; run the network probe to refresh.")
    result = decode(frames[0])
    assert isinstance(result, bytes)


def test_decode_passthrough_when_no_compression_used() -> None:
    """A frame whose payload contains only sub-256 characters round-trips.

    The decoder treats any input character with ord < 256 as a literal — so
    pure-ASCII JSON with no LZW back-references decodes to itself. This
    isolates the decoder algorithm from the upstream-fixture dependency.
    """
    from observatory.pollers.blitzortung.decoder import decode

    pure_ascii = b'{"time":1,"lat":2,"lon":3}'
    assert decode(pure_ascii) == pure_ascii
