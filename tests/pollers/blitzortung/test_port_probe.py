"""Live Blitzortung WebSocket port probe (network-gated, manual-run).

Resolves 05-RESEARCH Open Question 1: is the volunteer pool reachable on
the standard ``wss://`` port (443) or on the legacy ``:8056``?

Run with::

    uv run pytest tests/pollers/blitzortung/test_port_probe.py -m network -s

The probe writes ``BLITZORTUNG_PORT_PROBE.md`` next to this file with the
working URL(s), a short hex preview of the first received frame, and the
capture command that refreshed ``tests/fixtures/blitzortung/sample_frames.bin``.

Skipped by default — the ``addopts = "-m 'not network'"`` filter in
``pyproject.toml`` deselects ``@pytest.mark.network`` so CI never blocks on
upstream availability.
"""

from __future__ import annotations

import json
import ssl
import struct
import time
from pathlib import Path

import pytest

websockets_sync = pytest.importorskip("websockets.sync.client")

HERE = Path(__file__).parent
PROBE_DOC = HERE / "BLITZORTUNG_PORT_PROBE.md"
FIXTURE = HERE.parent.parent / "fixtures" / "blitzortung" / "sample_frames.bin"
SUBSCRIBE = '{"a": 111}'
HOSTS = ("ws1.blitzortung.org", "ws3.blitzortung.org", "ws7.blitzortung.org", "ws8.blitzortung.org")
# (scheme, port, verify_ssl) — Blitzortung's volunteer pool has historically
# used self-signed or expired certs; the community decoder writeups (gkbrk,
# SimonSchick) connect with verification relaxed. We try strict first.
ENDPOINT_VARIANTS = (
    ("wss", 443, True),
    ("wss", 443, False),
    ("ws", 8056, None),
)
TARGET_FRAMES = 5
MAX_WAIT_SEC = 30.0


def _probe(
    scheme: str,
    host: str,
    port: int,
    verify: bool | None,
    timeout: float = 10.0,
) -> tuple[bool, list[bytes], str]:
    """Open WS, send subscribe, collect frames for up to MAX_WAIT_SEC.

    Returns (ok, frames, error_msg).
    """
    frames: list[bytes] = []
    url = f"{scheme}://{host}:{port}"
    ssl_ctx: ssl.SSLContext | None
    if scheme == "wss":
        ssl_ctx = ssl.create_default_context()
        if verify is False:
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
    else:
        ssl_ctx = None
    try:
        with websockets_sync.connect(url, ssl=ssl_ctx, open_timeout=timeout) as ws:
            ws.send(SUBSCRIBE)
            deadline = time.monotonic() + MAX_WAIT_SEC
            while time.monotonic() < deadline and len(frames) < TARGET_FRAMES:
                try:
                    msg = ws.recv(timeout=5.0)
                except TimeoutError:
                    continue
                raw = msg if isinstance(msg, bytes) else msg.encode()
                frames.append(raw)
        return (len(frames) > 0, frames, "")
    except Exception as exc:  # pragma: no cover — diagnostic
        return (False, frames, f"{type(exc).__name__}: {exc}")


@pytest.mark.network
def test_probe_blitzortung_endpoints() -> None:
    """Probe every host x port combo and record the working set."""
    results: list[dict] = []
    captured: list[bytes] = []
    captured_from: str | None = None

    for host in HOSTS:
        for scheme, port, verify in ENDPOINT_VARIANTS:
            url = f"{scheme}://{host}:{port}"
            verify_label = "verify=on" if verify else ("verify=off" if verify is False else "plain")
            ok, frames, err = _probe(scheme, host, port, verify)
            results.append(
                {
                    "url": f"{url} ({verify_label})",
                    "ok": ok,
                    "frames": len(frames),
                    "first_bytes_hex": frames[0][:32].hex() if frames else "",
                    "error": err,
                }
            )
            if ok and len(frames) >= TARGET_FRAMES and not captured:
                captured = frames[:TARGET_FRAMES]
                captured_from = f"{url} ({verify_label})"

    # Persist record (always — even on failure, the operator wants the log).
    lines = [
        "# Blitzortung WebSocket port probe result",
        "",
        f"**Probed:** {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
        f"**Hosts:** {', '.join(HOSTS)}",
        f"**Endpoints per host:** {', '.join(f'{s}://*:{p}' for s, p, _ in ENDPOINT_VARIANTS)}",
        f"**Subscribe message:** `{SUBSCRIBE}`",
        f"**Target frames per probe:** {TARGET_FRAMES}",
        f"**Max wait per probe:** {MAX_WAIT_SEC:.0f}s",
        "",
        "## Per-endpoint result",
        "",
        "| URL | Ok | Frames | First 32 bytes (hex) | Error |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        err_short = (r["error"][:80] + "...") if len(r["error"]) > 80 else r["error"]
        lines.append(
            f"| `{r['url']}` | {'✅' if r['ok'] else '❌'} | {r['frames']} | "
            f"`{r['first_bytes_hex']}` | {err_short or '—'} |"
        )

    lines += [
        "",
        "## Capture",
        "",
    ]
    if captured:
        lines += [
            f"Captured **{len(captured)} frame(s)** from `{captured_from}` "
            f"into `tests/fixtures/blitzortung/sample_frames.bin`.",
            "",
            "**Encoding:** length-prefixed (4-byte big-endian u32 length + frame bytes), "
            "concatenated. Loader: see `tests/pollers/blitzortung/conftest.py::load_frames`.",
            "",
            "**Capture command:** `uv run pytest tests/pollers/blitzortung/test_port_probe.py "
            "-m network -s`",
        ]
    else:
        lines += [
            "**No frames captured.** Existing fixture (if any) left untouched.",
            "Service must degrade gracefully (Task 5 covers this path).",
        ]

    lines += [
        "",
        "## Settings impact",
        "",
        "If 8056 is the working port (and 443 isn't), update "
        "`observatory/config.py::settings.poller_blitzortung_ws_urls` defaults "
        "(prepend `:8056` to each host).",
        "",
    ]

    PROBE_DOC.write_text("\n".join(lines) + "\n")

    if captured:
        # Length-prefixed encoding so the decoder test can split frames cleanly.
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        buf = bytearray()
        for f in captured:
            buf += struct.pack(">I", len(f))
            buf += f
        FIXTURE.write_bytes(bytes(buf))

    # Don't fail the test if the upstream is unreachable — record + degrade.
    # Operator reads BLITZORTUNG_PORT_PROBE.md to decide next step.
    if not captured:
        pytest.skip(
            "No frames captured from any endpoint; see BLITZORTUNG_PORT_PROBE.md. "
            "Service will rely on graceful-degradation path."
        )

    # Sanity: at least one frame should be JSON-decodable AFTER LZW decoding.
    # We can't test that here (decoder lives in Task 2), but we can assert the
    # frame is non-trivial.
    assert all(len(f) > 4 for f in captured), "captured frames look truncated"
    # Defensive: ensure subscribe payload happened (sanity).
    assert json.loads(SUBSCRIBE)["a"] == 111
