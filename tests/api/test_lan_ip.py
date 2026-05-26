"""Phase 6 Plan 06-02 — Tests for resolve_lan_ip() in observatory.api.__main__.

The implementation uses the "UDP-connect trick": create a SOCK_DGRAM socket,
connect to a TEST-NET address (no packets sent), then read getsockname()
to get the outbound interface's IP. Falls back to getaddrinfo() if the
socket creation/connect fails (e.g. in restrictive CI sandboxes).
"""

from __future__ import annotations

import socket
from typing import Any
from unittest.mock import MagicMock

import pytest

from observatory.api.__main__ import resolve_lan_ip


class _FakeSocket:
    """Minimal stand-in for socket.socket used by resolve_lan_ip()."""

    def __init__(self, getsockname_addr: str, raise_on_connect: bool = False) -> None:
        self._addr = getsockname_addr
        self._raise = raise_on_connect
        self.closed = False

    def connect(self, _target: Any) -> None:
        if self._raise:
            raise OSError("network unreachable")

    def getsockname(self) -> tuple[str, int]:
        return (self._addr, 0)

    def close(self) -> None:
        self.closed = True


def test_udp_trick_returns_lan_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    """Standard happy path: UDP-connect trick reveals the LAN IP."""
    fake = _FakeSocket("192.168.1.42")
    monkeypatch.setattr(socket, "socket", lambda *_a, **_k: fake)
    assert resolve_lan_ip() == "192.168.1.42"
    assert fake.closed


def test_udp_trick_returns_10_dot(monkeypatch: pytest.MonkeyPatch) -> None:
    """10.x.x.x is a valid LAN IP — not filtered."""
    fake = _FakeSocket("10.0.0.5")
    monkeypatch.setattr(socket, "socket", lambda *_a, **_k: fake)
    assert resolve_lan_ip() == "10.0.0.5"


def test_udp_trick_loopback_falls_back_to_getaddrinfo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If UDP trick yields 127.x, fall back to getaddrinfo()."""
    fake = _FakeSocket("127.0.1.1")
    monkeypatch.setattr(socket, "socket", lambda *_a, **_k: fake)
    monkeypatch.setattr(socket, "gethostname", lambda: "fake-host")
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_a, **_k: [
            (0, 0, 0, "", ("127.0.0.1", 0)),
            (0, 0, 0, "", ("192.168.7.7", 0)),
        ],
    )
    assert resolve_lan_ip() == "192.168.7.7"


def test_udp_trick_oserror_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """connect() raising OSError → fallback path used."""
    fake = _FakeSocket("0.0.0.0", raise_on_connect=True)
    monkeypatch.setattr(socket, "socket", lambda *_a, **_k: fake)
    monkeypatch.setattr(socket, "gethostname", lambda: "fake-host")
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_a, **_k: [(0, 0, 0, "", ("172.16.0.9", 0))],
    )
    assert resolve_lan_ip() == "172.16.0.9"
    assert fake.closed


def test_both_paths_exhausted_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """UDP trick + getaddrinfo both yield only loopback → RuntimeError."""
    fake = _FakeSocket("127.0.0.1")
    monkeypatch.setattr(socket, "socket", lambda *_a, **_k: fake)
    monkeypatch.setattr(socket, "gethostname", lambda: "my-pi")
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_a, **_k: [(0, 0, 0, "", ("127.0.0.1", 0))],
    )
    with pytest.raises(RuntimeError, match="my-pi"):
        resolve_lan_ip()


def test_getaddrinfo_oserror_wrapped(monkeypatch: pytest.MonkeyPatch) -> None:
    """If fallback getaddrinfo() raises OSError, surface as RuntimeError."""
    fake = _FakeSocket("127.0.0.1")
    monkeypatch.setattr(socket, "socket", lambda *_a, **_k: fake)
    monkeypatch.setattr(socket, "gethostname", lambda: "my-pi")

    def _raises(*_a: Any, **_k: Any) -> Any:
        raise OSError("name resolution failed")

    monkeypatch.setattr(socket, "getaddrinfo", _raises)
    with pytest.raises(RuntimeError, match="my-pi"):
        resolve_lan_ip()


def test_socket_is_closed_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Socket from the UDP trick is closed even when path succeeds."""
    close_mock = MagicMock()
    fake = _FakeSocket("192.168.0.95")
    fake.close = close_mock  # type: ignore[method-assign]
    monkeypatch.setattr(socket, "socket", lambda *_a, **_k: fake)
    resolve_lan_ip()
    close_mock.assert_called_once()
