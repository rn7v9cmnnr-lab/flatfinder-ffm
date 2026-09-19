"""WhatsApp Business Cloud API.

WICHTIG - drei Dinge, die dich sonst ueberraschen:

1. VORLAGENZWANG. Eine vom Bot ausgehende Nachricht ausserhalb des
   24-Stunden-Fensters MUSS eine von Meta freigegebene Vorlage sein.
   Freitext geht nur, nachdem DU geschrieben hast.

2. KOSTEN. Utility-Vorlagen kosten in Deutschland rund 0,055 USD pro
   Nachricht - einer der teuersten Maerkte. 40 Angebote/Tag ~ 66 USD/Monat.
   Deshalb: Score-Schwelle hochsetzen, nicht jedes Angebot melden.

3. Seit 01.10.2026 sind auch Service-Antworten eines Drittanbieter-Agenten
   im 24h-Fenster kostenpflichtig. Der frueher uebliche Trick "erst selbst
   schreiben, dann ist alles gratis" traegt nicht mehr.

Die Vorlage muss vorab im Meta Business Manager angelegt und freigegeben
werden. Kategorie UTILITY (nicht MARKETING - billiger und wird eher
genehmigt). Vorlagentext z.B.:

    Neues Wohnungsangebot: {{1}}
    {{2}}
    {{3}}
    Score {{4}}
    Bewerben?

  Buttons: Quick Reply "Ja, bewerben" | Quick Reply "Nein"

Die Button-Antwort kommt als Webhook mit button_reply.id - darin steckt
unsere application_id, weil Meta die Payload durchreicht.
"""

from __future__ import annotations

import logging

import httpx

from ..config import Settings
from ..models import Listing
from .base import Answer, Messenger

log = logging.getLogger(__name__)

GRAPH = "https://graph.facebook.com/v21.0"


class WhatsAppMessenger(Messenger):
    name = "whatsapp"

    def __init__(self, settings: Settings) -> None:
        self.phone_id = settings.whatsapp_phone_number_id
        self.token = settings.whatsapp_access_token
        self.to = settings.whatsapp_recipient
        self.template = settings.whatsapp_template_name

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"}

    async def ask(self, listing: Listing, application_id: int, reasons: list[str]) -> str:
        eckdaten = " · ".join(x for x in [
            f"{listing.rooms:.0f} Zi" if listing.rooms else "",
            f"{listing.sqm:.0f} m²" if listing.sqm else "",
            f"{listing.price_cold} € kalt" if listing.price_cold else "",
        ] if x)
        lage = f"{listing.zip or ''} {listing.district or listing.city or ''}".strip()

        body = {
            "messaging_product": "whatsapp",
            "to": self.to,
            "type": "template",
            "template": {
                "name": self.template,
                "language": {"code": "de"},
                "components": [
                    {"type": "body", "parameters": [
                        {"type": "text", "text": listing.title[:60]},
                        {"type": "text", "text": eckdaten or "-"},
                        {"type": "text", "text": lage or "-"},
                        {"type": "text", "text": str(listing.score or 0)},
                    ]},
                    # Die Payload kommt in der Webhook-Antwort zurueck -
                    # so finden wir die Bewerbung wieder.
                    {"type": "button", "sub_type": "quick_reply", "index": "0",
                     "parameters": [{"type": "payload", "payload": f"yes:{application_id}"}]},
                    {"type": "button", "sub_type": "quick_reply", "index": "1",
                     "parameters": [{"type": "payload", "payload": f"no:{application_id}"}]},
                ],
            },
        }
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(f"{GRAPH}/{self.phone_id}/messages",
                             headers=self._headers, json=body)
            if r.status_code >= 400:
                log.error("WhatsApp lehnt ab (%s): %s", r.status_code, r.text[:400])
            r.raise_for_status()
            return r.json()["messages"][0]["id"]

    async def notify(self, text: str) -> None:
        """Freitext - funktioniert NUR im 24h-Fenster nach deiner letzten
        Nachricht. Ausserhalb schlaegt das mit Fehler 131047 fehl; das ist
        erwartet und kein Bug."""
        body = {"messaging_product": "whatsapp", "to": self.to,
                "type": "text", "text": {"body": text[:4000]}}
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(f"{GRAPH}/{self.phone_id}/messages",
                             headers=self._headers, json=body)
            if r.status_code >= 400:
                log.warning("WhatsApp-Freitext abgelehnt (24h-Fenster zu?): %s",
                            r.text[:200])

    @staticmethod
    def parse_answer(payload: dict) -> Answer | None:
        """Meta schachtelt tief: entry[].changes[].value.messages[]"""
        try:
            for entry in payload.get("entry", []):
                for change in entry.get("changes", []):
                    for msg in (change.get("value", {}) or {}).get("messages", []):
                        inter = msg.get("interactive", {})
                        reply = inter.get("button_reply") or {}
                        data = reply.get("id") or ""
                        if ":" not in data:
                            continue
                        verdict, _, app_id = data.partition(":")
                        if verdict in ("yes", "no") and app_id.isdigit():
                            return Answer(int(app_id), verdict == "yes", data)
        except (AttributeError, TypeError) as e:
            log.warning("WhatsApp-Webhook unlesbar: %s", e)
        return None


def build(settings: Settings) -> Messenger:
    """Factory - liest MESSENGER aus .env."""
    from .telegram import TelegramMessenger
    if settings.messenger == "whatsapp":
        return WhatsAppMessenger(settings)
    return TelegramMessenger(settings)
