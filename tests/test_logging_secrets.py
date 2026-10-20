"""Secrets must never reach the logs (security audit 2026-10-20, M1/M2).

httpx's own logger prints `HTTP Request: POST <url>` at INFO, and production
runs the root logger at INFO. The Telegram bot token, the ntfy topic and the
home coordinates (Open-Meteo query string) all live IN request URLs, so they
were written to the journal on every alert/poll -- and the soak-snapshot timer
then persisted journal tails to the SD card.

Note on test design: under pytest, logging.basicConfig() is a no-op because
pytest has already attached handlers, so the root logger stays at WARNING and a
naive test passes even while the leak exists. These tests set the root to INFO
explicitly to reproduce production, and capture with their own handler.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr

from observatory.logging import configure_logging

FAKE_TOKEN = "123456789:FAKE-test-token-not-real-abcdefghijk"


class _Collect(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(record.getMessage())


@pytest.fixture
def production_logging() -> Iterator[_Collect]:
    """Root at INFO with a capturing handler, as on the Pi; restored afterwards."""
    root = logging.getLogger()
    saved_root = root.level
    saved = {n: logging.getLogger(n).level for n in ("httpx", "httpcore")}
    handler = _Collect()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    try:
        configure_logging("INFO")
        yield handler
    finally:
        root.removeHandler(handler)
        root.setLevel(saved_root)
        for name, level in saved.items():
            logging.getLogger(name).setLevel(level)


def test_http_request_urls_are_not_logged(production_logging: _Collect) -> None:
    """A request whose URL carries a secret must leave no trace in the logs."""
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": True}))
    with httpx.Client(transport=transport) as client:
        client.post(f"https://api.telegram.org/bot{FAKE_TOKEN}/sendMessage", json={})
        client.get("https://api.open-meteo.com/v1/forecast?latitude=51.5074&longitude=-0.1278")

    joined = "\n".join(production_logging.lines)
    assert FAKE_TOKEN not in joined, f"bot token reached the logs:\n{joined}"
    assert "51.5074" not in joined, f"coordinates reached the logs:\n{joined}"


def test_telegram_notifier_never_logs_the_token(
    production_logging: _Collect, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end through notify_telegram, on both the success and failure paths."""
    from observatory.weather.alerts import notifier

    monkeypatch.setattr(
        notifier,
        "settings",
        SimpleNamespace(
            alert_telegram_enabled=True,
            alert_telegram_bot_token=SecretStr(FAKE_TOKEN),
            alert_telegram_chat_id="42",
        ),
    )

    def make_client(handler: object) -> type[httpx.AsyncClient]:
        class _Mocked(httpx.AsyncClient):
            def __init__(self, *args: object, **kwargs: object) -> None:
                kwargs["transport"] = httpx.MockTransport(handler)  # type: ignore[arg-type]
                super().__init__(*args, **kwargs)  # type: ignore[arg-type]

        return _Mocked

    for handler in (
        lambda request: httpx.Response(200, json={"ok": True}),
        lambda request: httpx.Response(500, json={"ok": False}),
    ):
        monkeypatch.setattr(httpx, "AsyncClient", make_client(handler))
        asyncio.run(notifier.notify_telegram("Frost", "test body"))

    joined = "\n".join(production_logging.lines)
    assert FAKE_TOKEN not in joined, f"bot token reached the logs:\n{joined}"


def _service_modules() -> list[str]:
    import re
    from pathlib import Path

    units = Path(__file__).resolve().parent.parent / "deploy" / "systemd"
    mods: set[str] = set()
    for unit in units.glob("obs-*.service"):
        for m in re.finditer(r"^ExecStart=.*?-m ([\w.]+)", unit.read_text(), re.M):
            mods.add(m.group(1))
    return sorted(mods)


@pytest.mark.parametrize("module", _service_modules())
def test_every_service_entry_point_configures_logging(module: str) -> None:
    """Every unit's module must call configure_logging(): it is where the
    secret-leak guard above lives, and it gives one JSON log format. Two ops
    scripts skipped it and logged in console format, which silently defeated
    a grep for their JSON events during verification (2026-10-20)."""
    import importlib.util

    spec = importlib.util.find_spec(module)
    assert spec is not None and spec.origin, module
    origin = spec.origin
    if origin.endswith("__init__.py"):
        origin = origin.replace("__init__.py", "__main__.py")
    from pathlib import Path

    assert "configure_logging(" in Path(origin).read_text(), f"{module} never configures logging"
