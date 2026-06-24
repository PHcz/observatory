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
            await client.post(url, content=message.encode(), headers=headers)
    except Exception as exc:
        log.warning("ntfy.push_failed", error=str(exc))


async def notify_telegram(title: str, message: str) -> None:
    """Fire-and-forget Telegram push (second sanctioned outbound channel).

    Returns immediately when alert_telegram_enabled is False or the bot token /
    chat id are unset. Plain text (no parse_mode) so message punctuation never
    breaks Telegram's Markdown parser. Swallows ALL exceptions.

    Args:
        title:   First line of the message (bold-free; kept plain for safety).
        message: Body text.
    """
    if not settings.alert_telegram_enabled:
        return
    if not (settings.alert_telegram_bot_token and settings.alert_telegram_chat_id):
        log.warning("telegram.not_configured")
        return

    import httpx

    url = f"https://api.telegram.org/bot{settings.alert_telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": settings.alert_telegram_chat_id,
        "text": f"{title}\n{message}",
        "disable_web_page_preview": True,
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(url, json=payload)
    except Exception as exc:
        log.warning("telegram.push_failed", error=str(exc))


async def notify_all(title: str, message: str, priority: int = 4) -> None:
    """Fan a notification out to every enabled channel; never raises.

    Each channel is independently gated and self-contained (swallows its own
    errors), so one channel being down or disabled never affects the other.
    """
    await notify_ntfy(title, message, priority)
    await notify_telegram(title, message)
