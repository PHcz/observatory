# Blitzortung WebSocket port probe result

**Probed:** 2026-05-26T07:02:03Z
**Hosts:** ws1.blitzortung.org, ws3.blitzortung.org, ws7.blitzortung.org, ws8.blitzortung.org
**Endpoints per host:** wss://*:443, wss://*:443, ws://*:8056
**Subscribe message:** `{"a": 111}`
**Target frames per probe:** 5
**Max wait per probe:** 30s

## Per-endpoint result

| URL | Ok | Frames | First 32 bytes (hex) | Error |
|---|---|---|---|---|
| `wss://ws1.blitzortung.org:443 (verify=on)` | ❌ | 0 | `` | SSLCertVerificationError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify fa... |
| `wss://ws1.blitzortung.org:443 (verify=off)` | ✅ | 5 | `7b2274696d65223a31373739c48938393134c48d33c48a323830302c226c6174` | — |
| `ws://ws1.blitzortung.org:8056 (plain)` | ❌ | 0 | `` | ConnectionRefusedError: [Errno 61] Connection refused |
| `wss://ws3.blitzortung.org:443 (verify=on)` | ❌ | 0 | `` | SSLCertVerificationError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify fa... |
| `wss://ws3.blitzortung.org:443 (verify=off)` | ❌ | 0 | `` | InvalidStatus: server rejected WebSocket connection: HTTP 200 |
| `ws://ws3.blitzortung.org:8056 (plain)` | ❌ | 0 | `` | ConnectionRefusedError: [Errno 61] Connection refused |
| `wss://ws7.blitzortung.org:443 (verify=on)` | ❌ | 0 | `` | SSLCertVerificationError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify fa... |
| `wss://ws7.blitzortung.org:443 (verify=off)` | ✅ | 5 | `7b2274696d65223a31373739c4893839c48835c48d3530363330302c226c6174` | — |
| `ws://ws7.blitzortung.org:8056 (plain)` | ❌ | 0 | `` | ConnectionRefusedError: [Errno 61] Connection refused |
| `wss://ws8.blitzortung.org:443 (verify=on)` | ❌ | 0 | `` | SSLCertVerificationError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify fa... |
| `wss://ws8.blitzortung.org:443 (verify=off)` | ✅ | 5 | `7b2274696d65223a31373739c4893839303632c48b3436333830302c226c6174` | — |
| `ws://ws8.blitzortung.org:8056 (plain)` | ❌ | 0 | `` | ConnectionRefusedError: [Errno 61] Connection refused |

## Capture

Captured **5 frame(s)** from `wss://ws1.blitzortung.org:443 (verify=off)` into `tests/fixtures/blitzortung/sample_frames.bin`.

**Encoding:** length-prefixed (4-byte big-endian u32 length + frame bytes), concatenated. Loader: see `tests/pollers/blitzortung/conftest.py::load_frames`.

**Capture command:** `uv run pytest tests/pollers/blitzortung/test_port_probe.py -m network -s`

## Settings impact

**Working port: 443 (standard `wss://`)** on `ws1`, `ws7`, `ws8`. `ws3` rejected the WS handshake with HTTP 200 (probably parked); `ws://*:8056` is dead (ConnectionRefused) across the board. Defaults in `observatory/config.py::settings.poller_blitzortung_ws_urls` (no port suffix → 443) are correct — **no edit needed**.

## SSL note (important)

**Blitzortung's volunteer pool serves an invalid/self-signed certificate** — strict verification fails with `CERTIFICATE_VERIFY_FAILED`. Connecting with `verify=off` succeeds and frames flow normally. This matches community implementations (gkbrk, SimonSchick).

**Implementation impact (Task 5):** `BlitzortungClient` MUST construct its `ssl.SSLContext` with `check_hostname=False` and `verify_mode=ssl.CERT_NONE`, OR pass `ssl=False` equivalent. We accept this because:

- Blitzortung's ToS forbids republishing — payload integrity is not a security boundary for us
- The decoded JSON is parsed defensively (key whitelist, distance filter)
- There is no auth/credential exchange; an attacker MITMing the stream can only inject fake strikes (which we already drop via the radius filter for anything outside 500km)

The narrowed `verify=off` exposure is documented in `observatory/pollers/blitzortung/client.py` docstring.
