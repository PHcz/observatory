"""LZW-style decompressor for Blitzortung's obfuscated WebSocket frames.

Reverses the 11-line obfuscation per the gkbrk.com + SimonSchick community
writeups (05-RESEARCH §"Pattern 3"). Output is raw JSON bytes — callers
``json.loads`` the result.

Pure function: no I/O, no global state, deterministic. Verified against the
pinned real-frame fixture in ``tests/fixtures/blitzortung/sample_frames.bin``.
"""

from __future__ import annotations

# Ceiling on decoded output, in characters (security audit 2026-10-20, M6). Each
# dictionary entry is built from the previous output (e[o] = f + c), so a crafted
# frame whose codes always point at the newest entry grows quadratically -- ~16 KB
# in became 18 MB out and 74 MB peak memory. websockets' 1 MiB max_size limits
# the frame BEFORE inflation, so a ~100 KB frame could exhaust the Pi's 1.8 GB.
# Real frames decode to a few KB; this is ~450x headroom.
MAX_DECODED_CHARS = 4 * 1024 * 1024


class DecodeLimitError(ValueError):
    """A frame would decode past MAX_DECODED_CHARS; the caller drops it."""


def decode(b: bytes, max_chars: int = MAX_DECODED_CHARS) -> bytes:
    """Reverse Blitzortung's LZW-style obfuscation.

    The algorithm walks the input one character at a time, maintaining a
    dictionary of back-references whose entries start at index 256. A
    sub-256 character is a literal; anything else is a dictionary lookup
    or the fall-back ``f + c`` construction used when the encoder built
    the entry on the same step it referenced it.
    """
    e: dict[int, str] = {}
    d = list(b.decode())
    c = d[0]
    f = c
    g = [c]
    h = 256
    o = h
    total = len(c)
    for i in range(1, len(d)):
        a_int = ord(d[i])
        a: str = d[i] if h > a_int else (e[a_int] if a_int in e else f + c)
        total += len(a)
        if total > max_chars:
            # Stop before building it: the output and the dictionary both grow
            # with every step, so checking afterwards would be too late.
            raise DecodeLimitError(f"frame decodes to more than {max_chars} chars")
        g.append(a)
        c = a[0]
        e[o] = f + c
        o += 1
        f = a
    return "".join(g).encode()
