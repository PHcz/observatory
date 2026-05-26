"""Phase 6 Plan 06-02 — Tests for resolve_lan_ip() in observatory.api.__main__."""

from __future__ import annotations

import socket

import pytest

from observatory.api.__main__ import resolve_lan_ip


def test_returns_first_non_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    """First non-loopback IPv4 is returned; loopback entries are skipped."""
    monkeypatch.setattr(socket, "gethostname", lambda: "fake-host")
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [
            (0, 0, 0, "", ("192.168.1.42", 0)),
            (0, 0, 0, "", ("127.0.0.1", 0)),
        ],
    )
    assert resolve_lan_ip() == "192.168.1.42"


def test_only_loopback_raises_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """When all results are loopback, RuntimeError includes the hostname."""
    monkeypatch.setattr(socket, "gethostname", lambda: "my-pi")
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [(0, 0, 0, "", ("127.0.0.1", 0))],
    )
    with pytest.raises(RuntimeError, match="my-pi"):
        resolve_lan_ip()


def test_empty_getaddrinfo_raises_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty getaddrinfo result → RuntimeError."""
    monkeypatch.setattr(socket, "gethostname", lambda: "my-pi")
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [])
    with pytest.raises(RuntimeError):
        resolve_lan_ip()


def test_loopback_and_public_picks_non_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    """With both loopback and a public IP, the non-loopback is returned."""
    monkeypatch.setattr(socket, "gethostname", lambda: "my-pi")
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [
            (0, 0, 0, "", ("127.0.0.1", 0)),
            (0, 0, 0, "", ("203.0.113.5", 0)),
        ],
    )
    assert resolve_lan_ip() == "203.0.113.5"


def test_lan_ips_not_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    """10.x, 172.x, 192.168.x are NOT skipped — only 127. is loopback."""
    for lan_ip in ("10.0.0.1", "172.16.0.1", "192.168.100.5"):
        monkeypatch.setattr(socket, "gethostname", lambda: "my-pi")
        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda *a, ip=lan_ip, **k: [(0, 0, 0, "", (ip, 0))],
        )
        assert resolve_lan_ip() == lan_ip
