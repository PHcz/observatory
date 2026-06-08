"""Phase 16 ENH-04: ntfy push notifier — fire-and-forget, never raises.

ntfy is the one sanctioned outbound exception to the local-first rule
(CONTEXT.md §Specific Ideas). Off-screen frost/storm notifications reach the
operator when not looking at the dashboard.

Configuration (all in settings — set on Pi .env only, never commit real values):
    alert_ntfy_enabled  — default False; nothing sent when False
    alert_ntfy_url      — ntfy server base URL (default "https://ntfy.sh")
    alert_ntfy_topic    — topic name (default "observatory-alerts")
    alert_ntfy_token    — optional Bearer token (empty = no auth header)
"""

from __future__ import annotations

import structlog

from observatory.config import settings

log = structlog.get_logger(__name__)


async def notify_ntfy(
    title: str,
    message: str,
    priority: int = 4,
) -> None:
    """Fire-and-forget ntfy push notification.

    Returns immediately when alert_ntfy_enabled is False.
    Swallows ALL exceptions — a network failure must never kill the caller.

    Args:
        title:    Notification title (ntfy Title header).
        message:  Notification body text.
        priority: ntfy priority (1=min, 5=max); default 4 = high.
    """
    if not settings.alert_ntfy_enabled:
        return

    import httpx

    url = f"{settings.alert_ntfy_url}/{settings.alert_ntfy_topic}"
    headers: dict[str, str] = {
        "Title": title,
        "Priority": str(priority),
    }
    if settings.alert_ntfy_token:
        headers["Authorization"] = f"Bearer {settings.alert_ntfy_token}"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(url, data=message.encode(), headers=headers)
    except Exception as exc:
        log.warning("ntfy.push_failed", error=str(exc))
