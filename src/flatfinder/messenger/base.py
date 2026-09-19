"""Messenger-Vertrag.

WhatsApp ist das Ziel, Telegram der Entwicklungskanal. Beide erfuellen
dieses Interface, der Rest des Codes kennt den Unterschied nicht.

Warum beide: eine WhatsApp-Vorlage muss von Meta freigegeben werden, das
dauert Stunden bis Tage. Waehrend der Entwicklung willst du nicht auf Meta
warten und nicht fuer jeden Testlauf ~0,055 USD zahlen. Telegram kostet
nichts und ist sofort da. Umschalten per MESSENGER=whatsapp in .env.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass

from ..models import Listing


@dataclass(frozen=True)
class Answer:
    """Eine eingehende Ja/Nein-Antwort, kanalunabhaengig."""
    application_id: int
    yes: bool
    raw: str


class Messenger(abc.ABC):
    name: str

    @abc.abstractmethod
    async def ask(self, listing: Listing, application_id: int, reasons: list[str]) -> str:
        """Angebot melden und nach Ja/Nein fragen.
        Gibt die Nachrichten-ID zurueck (fuer die Zuordnung der Antwort)."""

    @abc.abstractmethod
    async def notify(self, text: str) -> None:
        """Reine Information, ohne Rueckfrage."""

    @staticmethod
    def parse_answer(payload: dict) -> Answer | None:
        """Webhook-Payload -> Answer. Pro Kanal ueberschrieben."""
        raise NotImplementedError


def summary(listing: Listing, reasons: list[str]) -> str:
    """Der Text, den du auf dem Handy siehst. Muss in 5 Sekunden lesbar sein -
    du entscheidest oft unterwegs."""
    zeilen = [
        f"*{listing.title[:70]}*",
        "",
        f"{listing.rooms:.0f} Zimmer · {listing.sqm:.0f} m²" if listing.rooms and listing.sqm else "",
        f"{listing.price_cold} € kalt" + (
            f" · {listing.price_per_sqm:.2f} €/m²" if listing.price_per_sqm else ""
        ) if listing.price_cold else "",
        f"{listing.zip or ''} {listing.district or listing.city or ''}".strip(),
        "",
        f"Score {listing.score}: {'; '.join(reasons[:3])}" if listing.score else "",
        "",
        listing.url,
    ]
    return "\n".join(z for z in zeilen if z)
