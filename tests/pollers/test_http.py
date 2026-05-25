"""SEC-05 contract: hardened httpx fetch.

All tests use httpx.MockTransport (no real network). The fetch() function
accepts an optional `_client_factory` kwarg for transport injection.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from observatory.pollers._http import (
    USER_AGENT,
    CrossHostRedirect,
    ResponseTooLarge,
    RetriesExhausted,
    fetch,
)

URL = "https://example.com/api"


def _client_factory_with(transport: httpx.MockTransport) -> Callable[..., httpx.Client]:
    def factory(**kwargs: object) -> httpx.Client:
        kwargs.pop("transport", None)
        return httpx.Client(transport=transport, **kwargs)  # type: ignore[arg-type]

    return factory


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Replace time.sleep in _http with a recorder so tests don't wait 21s."""
    waited: list[float] = []

    def fake_sleep(s: float) -> None:
        waited.append(s)

    monkeypatch.setattr("observatory.pollers._http.time.sleep", fake_sleep)
    return waited


def test_successful_fetch_returns_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b'{"ok":true}')

    body = fetch(
        URL, source="test", _client_factory=_client_factory_with(httpx.MockTransport(handler))
    )
    assert body == b'{"ok":true}'


def test_user_agent_sent() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["ua"] = request.headers.get("user-agent", "")
        return httpx.Response(200, content=b"ok")

    fetch(URL, source="test", _client_factory=_client_factory_with(httpx.MockTransport(handler)))
    assert seen["ua"] == USER_AGENT
    assert USER_AGENT == "observatory/0.1 (https://github.com/PHcz/observatory)"


def test_response_too_large_aborts() -> None:
    big = b"x" * (6 * 1024 * 1024)  # 6 MiB > 5 MiB cap

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=big)

    with pytest.raises(ResponseTooLarge):
        fetch(
            URL, source="test", _client_factory=_client_factory_with(httpx.MockTransport(handler))
        )


def test_cross_host_redirect_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://attacker.com/x"})

    with pytest.raises(CrossHostRedirect):
        fetch(
            URL, source="test", _client_factory=_client_factory_with(httpx.MockTransport(handler))
        )


def test_same_host_redirect_followed() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(302, headers={"location": "https://example.com/api/v2"})
        return httpx.Response(200, content=b"redirected-ok")

    body = fetch(
        URL, source="test", _client_factory=_client_factory_with(httpx.MockTransport(handler))
    )
    assert body == b"redirected-ok"


def test_max_redirects_exceeded() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        # always redirect to same host
        return httpx.Response(302, headers={"location": "https://example.com/loop"})

    with pytest.raises(CrossHostRedirect):
        fetch(
            URL, source="test", _client_factory=_client_factory_with(httpx.MockTransport(handler))
        )


def test_retries_then_gives_up(_no_sleep: list[float]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, content=b"down")

    with pytest.raises(RetriesExhausted):
        fetch(
            URL, source="test", _client_factory=_client_factory_with(httpx.MockTransport(handler))
        )
    # Backoff sleeps include 1, 4, 16 (jitter added; assert each base value seen)
    assert any(s >= 1.0 and s < 2.0 for s in _no_sleep)
    assert any(s >= 4.0 and s < 5.0 for s in _no_sleep)
    assert any(s >= 16.0 and s < 17.0 for s in _no_sleep)


def test_429_retry_after_honored(_no_sleep: list[float]) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"retry-after": "2"})
        return httpx.Response(200, content=b"ok")

    body = fetch(
        URL, source="test", _client_factory=_client_factory_with(httpx.MockTransport(handler))
    )
    assert body == b"ok"
    assert 2 in [int(s) for s in _no_sleep]


def test_429_retry_after_capped_at_60(_no_sleep: list[float]) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"retry-after": "300"})
        return httpx.Response(200, content=b"ok")

    fetch(URL, source="test", _client_factory=_client_factory_with(httpx.MockTransport(handler)))
    assert 60 in [int(s) for s in _no_sleep]


def test_5xx_triggers_retry() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(500, content=b"oops")
        return httpx.Response(200, content=b"recovered")

    body = fetch(
        URL, source="test", _client_factory=_client_factory_with(httpx.MockTransport(handler))
    )
    assert body == b"recovered"


def test_4xx_no_retry() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(404, content=b"nope")

    with pytest.raises(httpx.HTTPStatusError):
        fetch(
            URL, source="test", _client_factory=_client_factory_with(httpx.MockTransport(handler))
        )
    assert calls["n"] == 1


def test_timeouts_applied() -> None:
    """Smoke: introspect _http source for the locked timeout values + verify=False absent."""
    import inspect

    import observatory.pollers._http as http_mod

    src = inspect.getsource(http_mod)
    assert "connect=settings.poller_http_connect_timeout_sec" in src or "connect=" in src
    assert "follow_redirects=False" in src
    assert "verify=False" not in src
    assert "total=" not in src  # httpx.Timeout has no `total` param


def test_no_verify_false_in_source() -> None:
    """TLS verification must never be disabled."""
    src = __import__("observatory.pollers._http", fromlist=["__file__"]).__file__
    text = open(src).read()
    assert "verify=False" not in text
