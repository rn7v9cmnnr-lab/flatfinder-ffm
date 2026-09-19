"""Telegram. Kostenlos, Inline-Buttons nativ, keine Freigabe noetig.

Setup (5 Minuten):
  1. In Telegram @BotFather anschreiben, /newbot, Namen vergeben
  2. Token in .env als TELEGRAM_BOT_TOKEN
  3. Dem eigenen Bot einmal /start schreiben
  4. https://api.telegram.org/bot<TOKEN>/getUpdates aufrufen -> chat.id
     in .env als TELEGRAM_CHAT_ID
"""

from __future__ import annotations

import httpx

from ..config import Settings
from ..models import Listing
from .base import Answer, Messenger, summary

API = "https://api.telegram.org/bot{token}/{method}"


class TelegramMessenger(Messenger):
    name = "telegram"

    def __init__(self, settings: Settings) -> None:
        self.token = settings.telegram_bot_token
        self.chat_id = settings.telegram_chat_id

    def _url(self, method: str) -> str:
        return API.format(token=self.token, method=method)

    async def ask(self, listing: Listing, application_id: int, reasons: list[str]) -> str:
        keyboard = {
            "inline_keyboard": [[
                {"text": "✅ Ja, bewerben", "callback_data": f"yes:{application_id}"},
                {"text": "❌ Nein",          "callback_data": f"no:{application_id}"},
            ]]
        }
        body = {
            "chat_id": self.chat_id,
            "text": summary(listing, reasons),
            "parse_mode": "Markdown",
            "reply_markup": keyboard,
            "disable_web_page_preview": False,
        }
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(self._url("sendMessage"), json=body)
            r.raise_for_status()
            return str(r.json()["result"]["message_id"])

    async def notify(self, text: str) -> None:
        async with httpx.AsyncClient(timeout=15) as c:
            await c.post(self._url("sendMessage"),
                         json={"chat_id": self.chat_id, "text": text,
                               "parse_mode": "Markdown"})

    @staticmethod
    def parse_answer(payload: dict) -> Answer | None:
        cb = payload.get("callback_query")
        if not cb:
            return None
        data = cb.get("data", "")
        if ":" not in data:
            return None
        verdict, _, app_id = data.partition(":")
        if verdict not in ("yes", "no") or not app_id.isdigit():
            return None
        return Answer(application_id=int(app_id), yes=verdict == "yes", raw=data)
