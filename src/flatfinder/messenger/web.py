"""Kein Messenger - die Weboberflaeche ist der Kanal.

Standard. Treffer landen in der Datenbank und erscheinen im Dashboard.
Kein Token, kein Meta-Konto, keine Kosten, kein Sperr-Risiko.

Telegram oder WhatsApp lassen sich jederzeit per MESSENGER=telegram bzw.
=whatsapp dazuschalten, ohne dass sich am uebrigen Code etwas aendert.
"""

from __future__ import annotations

import logging

from ..models import Listing
from .base import Messenger

log = logging.getLogger(__name__)


class WebMessenger(Messenger):
    name = "web"

    async def ask(self, listing: Listing, application_id: int, reasons: list[str]) -> str:
        # Im Alarm-Modus nie aufgerufen. Falls doch jemand NOTIFY_ONLY=false
        # setzt, ohne einen echten Messenger zu konfigurieren: die Bewerbung
        # wartet dann im Dashboard auf eine Entscheidung.
        log.info("Neue Bewerbung #%s wartet im Dashboard: %s",
                 application_id, listing.title[:60])
        return f"web-{application_id}"

    async def notify(self, text: str) -> None:
        # Der Treffer steht bereits in der DB und damit im Dashboard.
        log.info("Treffer: %s", text.splitlines()[0].strip("*") if text else "")
