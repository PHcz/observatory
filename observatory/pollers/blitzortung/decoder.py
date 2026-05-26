"""LZW-style decompressor for Blitzortung's obfuscated WebSocket frames.

Reverses the 11-line obfuscation per the gkbrk.com + SimonSchick community
writeups (05-RESEARCH §"Pattern 3"). Output is raw JSON bytes — callers
``json.loads`` the result.

Pure function: no I/O, no global state, deterministic. Verified against the
pinned real-frame fixture in ``tests/fixtures/blitzortung/sample_frames.bin``.
"""

from __future__ import annotations


def decode(b: bytes) -> bytes:
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
    for i in range(1, len(d)):
        a_int = ord(d[i])
        a: str = d[i] if h > a_int else (e[a_int] if a_int in e else f + c)
        g.append(a)
        c = a[0]
        e[o] = f + c
        o += 1
        f = a
    return "".join(g).encode()
