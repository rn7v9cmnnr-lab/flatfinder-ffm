"""Bewerbungstext generieren - mit Claude Opus 5.

Die Qualitaetsregeln stehen im System-Prompt und sind der eigentliche Wert
dieser Datei. Wer sie aendert, aendert die Rueckmeldequote. Vor jeder
Aenderung: alten und neuen Text nebeneinander legen (scripts/preview_text.py).

Kosten: rund 2 Cent pro Bewerbung. Bei 60 Bewerbungen im Monat ~1,20 EUR.
Der System-Prompt ist gecacht, weil er sich zwischen Objekten nicht aendert.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from ..config import Profile, Settings
from ..models import Listing

log = logging.getLogger(__name__)


class Bewerbung(BaseModel):
    subject: str = Field(description="Betreffzeile, max. 80 Zeichen, nennt Objekt und Ort")
    body: str = Field(description="Der Bewerbungstext, 120-180 Woerter, mit Anrede und Grussformel")
    hook: str = Field(description="Welches konkrete Detail aus dem Inserat wurde aufgegriffen")


SYSTEM = """\
Du schreibst Bewerbungen auf Mietwohnungen in Frankfurt am Main.

Der Empfaenger ist ein Vermieter oder Makler, der auf dieselbe Anzeige 80 bis
250 Zuschriften bekommt und jede davon maximal 30 Sekunden ansieht. Dein Text
hat genau eine Aufgabe: es auf den Stapel "Besichtigung einladen" zu schaffen.

REGELN

1. 120 bis 180 Woerter. Kuerzer ist besser als vollstaendiger.
2. Die ersten zwei Saetze enthalten die harten Fakten: Beruf, gesichertes
   Einkommen, Haushaltsgroesse, Einzugstermin. Ein Vermieter sucht zuerst
   einen zahlungsfaehigen Mieter, nicht einen netten Menschen.
3. Genau EIN konkreter Bezug zum Objekt aus den Anzeigendaten - Stadtteil,
   Grundriss, Etage, eine Ausstattungsbesonderheit. Das ist das einzige
   Signal, dass hier kein Serienbrief kommt. Steht in der Anzeige nichts
   Konkretes, nimm die Lage und werde nicht erfinderisch.
4. Unterlagen aktiv anbieten und aufzaehlen. "Auf Anfrage" ist wertlos -
   wer nachreichen muss, fliegt bei der Vorauswahl raus.
5. Konkrete Besichtigungsbereitschaft, kein "bei Interesse melde ich mich".
6. Hoefliches Sie. Ohne Anbiederung, ohne Ausrufezeichen, ohne Emojis.

VERBOTEN

- "Mit grossem Interesse habe ich Ihre Anzeige gelesen" und jede andere
  Floskel, die in jeder zweiten Zuschrift steht.
- Superlative ueber die Wohnung ("Traumwohnung", "perfekt fuer uns").
- Die eigene Lebensgeschichte, Hobbys, Zukunftsplaene.
- Jede Behauptung, die nicht in den Bewerberdaten steht. Du erfindest
  NIEMALS Einkommen, Beruf, Referenzen, Haustierfreiheit oder Ruhebeduerfnis.
  Fehlt eine Angabe, laesst du sie weg. Ein Vermieter, der eine erfundene
  Angabe bemerkt, sortiert sofort aus - und der Bewerber haftet dafuer.
- Erfundene Details ueber das Objekt. Nur benutzen, was in den Daten steht.

Schreibe naturales Deutsch. Ein Mensch mit dem angegebenen Beruf soll das
geschrieben haben koennen.\
"""


def _profile_block(p: Profile) -> str:
    """Nur gefuellte Felder. Leere Felder erscheinen nicht, damit das Modell
    nicht in Versuchung kommt, sie zu fuellen."""
    zeilen = [
        ("Name", p.full_name),
        ("Beruf", p.occupation),
        ("Arbeitgeber", p.employer),
        ("Haushaltsnettoeinkommen", f"{p.net_income} EUR/Monat" if p.net_income else ""),
        ("Haushalt", f"{p.household_size} Person(en)" if p.household_size else ""),
        ("Zum Haushalt", p.household_detail),
        ("Einzug moeglich", p.move_in_from),
        ("Unterlagen liegen vor", p.docs_ready),
        ("SCHUFA", "liegt vor" if p.schufa_available else ""),
        ("Besichtigung moeglich", p.viewing_availability),
        ("Sonstiges", p.extra_notes),
        ("Kontakt", " / ".join(x for x in (p.email, p.phone) if x)),
    ]
    return "\n".join(f"- {k}: {v}" for k, v in zeilen if v)


def _listing_block(l: Listing) -> str:
    zeilen = [
        ("Titel der Anzeige", l.title),
        ("Adresse", l.street),
        ("PLZ/Ort", " ".join(x for x in (l.zip, l.city) if x)),
        ("Stadtteil", l.district),
        ("Kaltmiete", f"{l.price_cold} EUR" if l.price_cold else ""),
        ("Warmmiete", f"{l.price_warm} EUR" if l.price_warm else ""),
        ("Wohnflaeche", f"{l.sqm:.1f} m2" if l.sqm else ""),
        ("Zimmer", f"{l.rooms:.0f}" if l.rooms else ""),
        ("Frei ab", l.available_from),
        ("Anbieter", l.source),
    ]
    out = "\n".join(f"- {k}: {v}" for k, v in zeilen if v)
    if l.description:
        # Beschreibung begrenzen: lange Exposes sind zu 90% Bauträger-Prosa
        # und verwaessern den Prompt.
        out += f"\n\nBeschreibung aus dem Inserat:\n{l.description[:1500]}"
    return out


class Composer:
    def __init__(self, settings: Settings, profile: Profile) -> None:
        self.settings = settings
        self.profile = profile
        # Erst hier importieren, nicht oben: das anthropic-SDK braucht
        # Python 3.10+, der Rest des Projekts laeuft ab 3.9. Im Alarm-Modus
        # (NOTIFY_ONLY=true, Standard) wird diese Klasse nie gebaut.
        try:
            import anthropic
        except ImportError as e:
            raise RuntimeError(
                "Fuer die Bewerbungstexte fehlt das anthropic-Paket. "
                "Installieren mit:  pip install -e \".[apply]\"  "
                "(braucht Python 3.10 oder neuer). "
                "Im Alarm-Modus wird es nicht gebraucht."
            ) from e
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key or None)

    def compose(self, listing: Listing) -> Bewerbung:
        """Schreibt den Bewerbungstext. Wirft bei API-Fehlern durch -
        der Aufrufer setzt die Bewerbung dann auf FAILED, statt etwas
        Halbfertiges zu verschicken."""
        user = (
            "BEWERBERDATEN\n"
            f"{_profile_block(self.profile)}\n\n"
            "ANZEIGE\n"
            f"{_listing_block(listing)}\n\n"
            "Schreibe die Bewerbung."
        )

        response = self._client.messages.parse(
            model=self.settings.anthropic_model,
            max_tokens=2000,          # ein Brief, kein Roman
            thinking={"type": "adaptive"},
            system=[{
                "type": "text",
                "text": SYSTEM,
                # Stabil ueber alle Objekte -> cachen. Greift erst ab der
                # Mindest-Prefixlaenge des Modells; schadet sonst nicht.
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": user}],
            output_format=Bewerbung,
        )
        # Optional absicherbar gegen Refusals durch den serverseitigen
        # Fallback: betas=["server-side-fallback-2026-07-01"], fallbacks="default"
        # ueber client.beta.messages. Fuer Bewerbungstexte praktisch nie noetig.

        result: Bewerbung = response.parsed_output
        log.info(
            "Text fuer %s generiert (%d Woerter, Hook: %s) | cache_read=%s",
            listing.key, len(result.body.split()), result.hook,
            getattr(response.usage, "cache_read_input_tokens", None),
        )
        return result
