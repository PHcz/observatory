"""Phase 16 ENH-04: ntfy push notifier — fire-and-forget, never raises.

RED: imports from observatory.weather.alerts.notifier which does not exist yet.
This test gates Wave 1 implementation.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from observatory.weather.alerts.notifier import notify_ntfy


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
            mock_settings.alert_ntfy_token = ""

            # Simulate a network failure
            mock_post = AsyncMock(side_effect=OSError("connection refused"))
            mock_instance = AsyncMock()
            mock_instance.post = mock_post
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_client_class.return_value.__aexit__ = AsyncMock(return_value=False)

            # Must not raise even when httpx raises
            asyncio.run(notify_ntfy(title="Test", message="test message"))
            # If we reach here, the error was swallowed correctly
