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


# --- Output cap (security audit 2026-10-20, M6) ------------------------------
# Every dictionary entry is built from the previous output (e[o] = f + c), so a
# crafted frame whose codes always point at the newest entry grows the output
# quadratically: a few KB in, tens of MB out, with the dictionary holding it all.
# websockets' 1 MiB max_size limits the frame BEFORE inflation, so it did not
# help; the Pi's 1.8 GB could be exhausted and the service OOM-killed.

import time  # noqa: E402

from observatory.pollers.blitzortung.decoder import (  # noqa: E402
    MAX_DECODED_CHARS,
    DecodeLimitError,
    decode,
)


def _quadratic_frame(n: int) -> bytes:
    """'a' then codes 256, 257, ... each resolving to the previous output + 'a'."""
    return ("a" + "".join(chr(256 + k) for k in range(n))).encode()


def test_quadratic_frame_is_refused_before_it_can_exhaust_memory() -> None:
    frame = _quadratic_frame(6000)  # ~12 KB in, ~18 M chars out if uncapped
    assert len(frame) < 20_000
    started = time.monotonic()
    with pytest.raises(DecodeLimitError):
        decode(frame)
    assert time.monotonic() - started < 2.0, "must stop early, not after building it all"


def test_decode_limit_error_is_a_value_error() -> None:
    """The client's frame handler drops anything decode raises; ValueError keeps
    that true for callers that only catch the documented decode failures."""
    assert issubclass(DecodeLimitError, ValueError)


def test_cap_leaves_ample_room_for_real_frames() -> None:
    """Real frames are ~9 KB; the cap must be orders of magnitude above that."""
    assert MAX_DECODED_CHARS >= 100 * 9_000
