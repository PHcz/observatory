"""Phase 16 ENH-04: ntfy push notifier — fire-and-forget, never raises.

RED: imports from observatory.weather.alerts.notifier which does not exist yet.
This test gates Wave 1 implementation.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import httpx
from pydantic import SecretStr
from structlog.testing import capture_logs

from observatory.weather.alerts.notifier import notify_ntfy, notify_telegram


class TestNtfyDisabled:
    def test_ntfy_disabled_noop(self) -> None:
        """When alert_ntfy_enabled=False, notify_ntfy returns without making any HTTP call."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client_class.return_value.__aenter__ = AsyncMock()
            mock_client_class.return_value.__aexit__ = AsyncMock()
            mock_post = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value.post = mock_post

            # settings.alert_ntfy_enabled is False by default in Settings
            asyncio.run(notify_ntfy(title="Test", message="test message"))

            mock_post.assert_not_called()


class TestNtfySwallowsErrors:
    def test_ntfy_swallows_network_errors(self) -> None:
        """Even when the HTTP call raises, notify_ntfy must NOT propagate the exception."""
        with (
            patch("observatory.weather.alerts.notifier.settings") as mock_settings,
            patch("httpx.AsyncClient") as mock_client_class,
        ):
            mock_settings.alert_ntfy_enabled = True
            mock_settings.alert_ntfy_url = "https://ntfy.sh"
            mock_settings.alert_ntfy_topic = "test-topic"
            mock_settings.alert_ntfy_token = SecretStr("")

            # Simulate a network failure
            mock_post = AsyncMock(side_effect=OSError("connection refused"))
            mock_instance = AsyncMock()
            mock_instance.post = mock_post
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

            # Must not raise even when httpx raises
            asyncio.run(notify_ntfy(title="Test", message="test message"))
            # If we reach here, the error was swallowed correctly


class TestTelegramDisabled:
    def test_telegram_disabled_noop(self) -> None:
        """alert_telegram_enabled=False (default) → no HTTP call."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_post = AsyncMock()
            mock_client_class.return_value.__aenter__ = AsyncMock(
                return_value=AsyncMock(post=mock_post)
            )
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)
            asyncio.run(notify_telegram(title="Test", message="hi"))
            mock_post.assert_not_called()

    def test_telegram_enabled_but_unconfigured_noop(self) -> None:
        """Enabled but token/chat_id empty → guarded, no HTTP call."""
        with (
            patch("observatory.weather.alerts.notifier.settings") as mock_settings,
            patch("httpx.AsyncClient") as mock_client_class,
        ):
            mock_settings.alert_telegram_enabled = True
            mock_settings.alert_telegram_bot_token = SecretStr("")
            mock_settings.alert_telegram_chat_id = ""
            mock_post = AsyncMock()
            mock_client_class.return_value.__aenter__ = AsyncMock(
                return_value=AsyncMock(post=mock_post)
            )
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)
            asyncio.run(notify_telegram(title="Test", message="hi"))
            mock_post.assert_not_called()


class TestTelegramSendsAndSwallows:
    def test_telegram_posts_to_send_message(self) -> None:
        """Fully configured → posts to the bot sendMessage endpoint with chat_id."""
        with (
            patch("observatory.weather.alerts.notifier.settings") as mock_settings,
            patch("httpx.AsyncClient") as mock_client_class,
        ):
            mock_settings.alert_telegram_enabled = True
            mock_settings.alert_telegram_bot_token = SecretStr("123:ABC")
            mock_settings.alert_telegram_chat_id = "999"
            mock_post = AsyncMock()
            mock_client_class.return_value.__aenter__ = AsyncMock(
                return_value=AsyncMock(post=mock_post)
            )
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

            asyncio.run(notify_telegram(title="Enviro Offline", message="no data"))

            mock_post.assert_called_once()
            args, kwargs = mock_post.call_args
            assert "/bot123:ABC/sendMessage" in args[0]
            assert kwargs["json"]["chat_id"] == "999"
            assert "Enviro Offline" in kwargs["json"]["text"]

    def test_telegram_swallows_network_errors(self) -> None:
        """A network failure must not propagate."""
        with (
            patch("observatory.weather.alerts.notifier.settings") as mock_settings,
            patch("httpx.AsyncClient") as mock_client_class,
        ):
            mock_settings.alert_telegram_enabled = True
            mock_settings.alert_telegram_bot_token = SecretStr("123:ABC")
            mock_settings.alert_telegram_chat_id = "999"
            mock_post = AsyncMock(side_effect=OSError("connection refused"))
            mock_client_class.return_value.__aenter__ = AsyncMock(
                return_value=AsyncMock(post=mock_post)
            )
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)
            asyncio.run(notify_telegram(title="Test", message="hi"))  # must not raise


class TestNtfyNonAsciiTitle:
    """HTTP headers are latin-1; a UTF-8 title must be RFC 2047 encoded.

    Regression: the CO2 alert title contains U+2082 (subscript two). httpx
    raised ``'ascii' codec can't encode character '\\u2082'``, notify_ntfy's
    blanket ``except Exception`` swallowed it into a warning, and every CO2
    alert was silently never delivered (observed on the Pi 2026-10-05).
    """

    @staticmethod
    def _post_headers(title: str) -> dict[str, str]:
        with (
            patch("observatory.weather.alerts.notifier.settings") as mock_settings,
            patch("httpx.AsyncClient") as mock_client_class,
        ):
            mock_settings.alert_ntfy_enabled = True
            mock_settings.alert_ntfy_url = "https://ntfy.sh"
            mock_settings.alert_ntfy_topic = "test-topic"
            mock_settings.alert_ntfy_token = SecretStr("")

            mock_post = AsyncMock()
            mock_instance = AsyncMock()
            mock_instance.post = mock_post
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

            asyncio.run(notify_ntfy(title=title, message="body"))

            mock_post.assert_called_once()
            headers = mock_post.call_args.kwargs["headers"]
            assert isinstance(headers, dict)
            return headers

    def test_non_ascii_title_is_header_safe(self) -> None:
        """The Title header must be encodable by httpx (ascii) and unfolded."""
        headers = self._post_headers("CO\u2082 high \u2014 living room")
        title = headers["Title"]
        title.encode("ascii")  # must not raise — this is what broke in production
        assert "\n" not in title and "\r" not in title, "folded header breaks HTTP"

    def test_non_ascii_title_round_trips(self) -> None:
        """Encoding must be reversible so the phone shows the real title."""
        from email.header import decode_header, make_header

        original = "CO\u2082 high \u2014 living room"
        decoded = str(make_header(decode_header(self._post_headers(original)["Title"])))
        assert decoded == original

    def test_ascii_title_left_untouched(self) -> None:
        """Plain ASCII titles must not be needlessly mangled into encoded-words."""
        assert self._post_headers("Frost warning")["Title"] == "Frost warning"


class TestRejectedPushesAreLogged:
    """The POST's response was never checked: Telegram answering 401 (revoked
    token) or 400 (bad chat id) looked exactly like a delivered alert, and
    ntfy 4xx/5xx likewise. Found while sending a test message 2026-10-20."""

    @staticmethod
    def _client_returning(response: httpx.Response) -> AsyncMock:
        return AsyncMock(post=AsyncMock(return_value=response))

    def test_telegram_rejection_is_logged_without_the_token(self) -> None:
        req = httpx.Request("POST", "https://api.telegram.org/botSECRET:TOKEN/sendMessage")
        resp = httpx.Response(401, json={"ok": False, "description": "Unauthorized"}, request=req)
        with (
            patch("observatory.weather.alerts.notifier.settings") as mock_settings,
            patch("httpx.AsyncClient") as mock_client_class,
            capture_logs() as logs,
        ):
            mock_settings.alert_telegram_enabled = True
            mock_settings.alert_telegram_bot_token = SecretStr("SECRET:TOKEN")
            mock_settings.alert_telegram_chat_id = "999"
            mock_client_class.return_value.__aenter__ = AsyncMock(
                return_value=self._client_returning(resp)
            )
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)
            asyncio.run(notify_telegram(title="T", message="m"))

        rejected = [e for e in logs if e["event"] == "telegram.push_rejected"]
        assert rejected and rejected[0]["status"] == 401
        assert rejected[0]["detail"] == "Unauthorized"
        assert "SECRET" not in str(logs)

    def test_telegram_success_is_logged(self) -> None:
        req = httpx.Request("POST", "https://api.telegram.org/botX/sendMessage")
        resp = httpx.Response(200, json={"ok": True}, request=req)
        with (
            patch("observatory.weather.alerts.notifier.settings") as mock_settings,
            patch("httpx.AsyncClient") as mock_client_class,
            capture_logs() as logs,
        ):
            mock_settings.alert_telegram_enabled = True
            mock_settings.alert_telegram_bot_token = SecretStr("X")
            mock_settings.alert_telegram_chat_id = "999"
            mock_client_class.return_value.__aenter__ = AsyncMock(
                return_value=self._client_returning(resp)
            )
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)
            asyncio.run(notify_telegram(title="T", message="m"))
        assert any(e["event"] == "telegram.push_sent" for e in logs)

    def test_ntfy_rejection_is_logged(self) -> None:
        req = httpx.Request("POST", "https://ntfy.sh/topic")
        resp = httpx.Response(403, text="forbidden", request=req)
        with (
            patch("observatory.weather.alerts.notifier.settings") as mock_settings,
            patch("httpx.AsyncClient") as mock_client_class,
            capture_logs() as logs,
        ):
            mock_settings.alert_ntfy_enabled = True
            mock_settings.alert_ntfy_url = "https://ntfy.sh"
            mock_settings.alert_ntfy_topic = "topic"
            mock_settings.alert_ntfy_token = SecretStr("")
            mock_client_class.return_value.__aenter__ = AsyncMock(
                return_value=self._client_returning(resp)
            )
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)
            asyncio.run(notify_ntfy(title="T", message="m"))
        rejected = [e for e in logs if e["event"] == "ntfy.push_rejected"]
        assert rejected and rejected[0]["status"] == 403
