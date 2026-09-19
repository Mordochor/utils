from __future__ import annotations

import urllib.parse
import urllib.request

from prague_housing.config import NotifySettings


def send_telegram(settings: NotifySettings, text: str, user_agent: str) -> None:
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return
    url = (
        f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage?"
        + urllib.parse.urlencode(
            {
                "chat_id": settings.telegram_chat_id,
                "text": text[:3900],
                "disable_web_page_preview": "true",
            }
        )
    )
    req = urllib.request.Request(url, headers={"User-Agent": user_agent}, method="GET")
    with urllib.request.urlopen(req, timeout=30) as response:
        response.read()
