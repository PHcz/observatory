"""Hardened httpx fetch shared by every Phase 4+ poller (SEC-05).

Hardening:
- TLS verification always on (httpx default; we never disable it)
- Explicit per-phase timeouts (connect/read/write/pool)
- follow_redirects=False; we handle redirects manually with a same-host check
- Streaming response with 5 MiB byte cap (configurable via settings)
- Fixed User-Agent for upstream contactability
- 4 attempts total (1 + 3 retries with 1/4/16s + jitter backoff)
- 429 honors Retry-After (capped at 60s); 5xx retried; 4xx propagated (no retry)

Note: httpx.Timeout has no aggregate field; the retry-loop sleep budget
(~21s) plus per-attempt timeouts (~25s worst case) effectively bound runtime.
"""

from __future__ import annotations

import random
import re
import time
from collections.abc import Callable
from urllib.parse import urljoin, urlparse

import httpx

from observatory.config import settings

USER_AGENT = "observatory/0.1 (https://github.com/PHcz/observatory)"

BACKOFF_SCHEDULE_SEC = (1.0, 4.0, 16.0)
RETRY_AFTER_CAP_SEC = 60


class ResponseTooLarge(Exception):
    """Streaming response exceeded the configured byte cap."""


class CrossHostRedirect(Exception):
    """Redirect target was off-host, or redirect chain exceeded the cap."""


class RetriesExhausted(Exception):
    """All retry attempts failed with a transient error."""


def _timeout() -> httpx.Timeout:
    return httpx.Timeout(
        connect=settings.poller_http_connect_timeout_sec,
        read=settings.poller_http_read_timeout_sec,
        write=5.0,
        pool=5.0,
    )


def _stream_with_cap(response: httpx.Response, cap: int) -> bytes:
    buf = bytearray()
    for chunk in response.iter_bytes(chunk_size=8192):
        buf.extend(chunk)
        if len(buf) > cap:
            raise ResponseTooLarge(f"response exceeded {cap} bytes")
    return bytes(buf)


_DELAY_SECONDS = re.compile(r"[0-9]{1,9}")
_DEFAULT_PORTS = {"http": 80, "https": 443}


def _origin(url: str) -> tuple[str, str | None, int | None]:
    parts = urlparse(url)
    return parts.scheme, parts.hostname, parts.port or _DEFAULT_PORTS.get(parts.scheme)


def _same_origin_or_upgrade(original: str, target: str) -> bool:
    """Follow a redirect only to the same scheme, host and port -- or an
    http -> https upgrade on the same host. Comparing the hostname alone let a
    redirect downgrade https to http or move to another port (audit F28)."""
    o_scheme, o_host, o_port = _origin(original)
    t_scheme, t_host, t_port = _origin(target)
    if t_host is None or t_host != o_host:
        return False
    if (t_scheme, t_port) == (o_scheme, o_port):
        return True
    return o_scheme == "http" and t_scheme == "https" and t_port == 443


def fetch(
    url: str,
    *,
    source: str,
    _client_factory: Callable[..., httpx.Client] | None = None,
) -> bytes:
    """Hardened GET. Returns body bytes. Raises RetriesExhausted on persistent transient failure.

    Args:
        url: absolute URL to fetch.
        source: short label for logging context (e.g. 'usgs').
        _client_factory: test hook; called with the same kwargs as httpx.Client.
            Defaults to httpx.Client.
    """
    factory: Callable[..., httpx.Client] = _client_factory or httpx.Client
    max_redirects = settings.poller_http_max_redirects
    max_bytes = settings.poller_http_max_response_bytes
    del source  # reserved for logging context; not used directly here

    last_exc: BaseException | None = None
    with factory(
        timeout=_timeout(),
        follow_redirects=False,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        # 4 attempts total: initial + 3 retries.
        attempts = [0.0, *BACKOFF_SCHEDULE_SEC]
        for sleep_s in attempts:
            if sleep_s > 0:
                time.sleep(sleep_s + random.uniform(0, 0.5))
            try:
                current_url = url
                redirects_followed = 0
                while True:
                    with client.stream("GET", current_url) as response:
                        status = response.status_code
                        if status in (301, 302, 303, 307, 308):
                            redirects_followed += 1
                            if redirects_followed > max_redirects:
                                raise CrossHostRedirect(
                                    f"too many redirects from {url} (cap={max_redirects})"
                                )
                            loc = response.headers.get("location")
                            if not loc:
                                raise httpx.HTTPError("redirect without Location header")
                            target = urljoin(current_url, loc)
                            if not _same_origin_or_upgrade(url, target):
                                raise CrossHostRedirect(
                                    f"redirect off-origin: {_origin(url)} -> {_origin(target)}"
                                )
                            current_url = target
                            continue
                        if status == 429:
                            ra = response.headers.get("retry-after")
                            # ASCII digits only: str.isdigit() also accepts
                            # superscripts, which int() then rejects (audit F29).
                            wait_s = (
                                min(int(ra), RETRY_AFTER_CAP_SEC)
                                if ra and _DELAY_SECONDS.fullmatch(ra)
                                else None
                            )
                            if wait_s is not None:
                                time.sleep(wait_s)
                                last_exc = httpx.HTTPStatusError(
                                    "429 rate-limited",
                                    request=response.request,
                                    response=response,
                                )
                                break  # retry outer attempt loop
                            response.raise_for_status()
                        if 500 <= status < 600:
                            response.raise_for_status()  # -> retry via except
                        response.raise_for_status()
                        return _stream_with_cap(response, max_bytes)
                # If we broke out of the inner while due to a 429-retry, loop attempts.
                continue
            except httpx.HTTPStatusError as exc:
                if 500 <= exc.response.status_code < 600 or exc.response.status_code == 429:
                    last_exc = exc
                    continue
                raise
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_exc = exc
                continue
            except (ResponseTooLarge, CrossHostRedirect):
                raise
    raise RetriesExhausted(f"all {len(attempts)} attempts failed: {last_exc!r}")
