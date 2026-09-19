"""Die Nahtstelle zwischen Track A (Finden) und Track B (Bewerben).

Diese Datei ist der Vertrag. Aenderungen hier betreffen beide Seiten und
gehoeren deshalb immer in einen eigenen PR mit Review vom jeweils anderen.
"""

from __future__ import annotations

from typing import List, Optional

import hashlib
import re
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator

from .compat import StrEnum


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Kind(StrEnum):
    """Was fuer eine Art Anbieter das ist.

    Bestimmt die Farbe in der Oberflaeche. Bewusst nur drei Farben plus
    neutral: mehr kategoriale Farben lassen sich nicht mehr zuverlaessig
    unterscheiden - geprueft mit dem Palettenvalidator, in hell und dunkel.
    """

    LANDLORD = "grossvermieter"   # vermietet selbst, nie Provision
    COOP = "genossenschaft"       # Genossenschaft, meist Anteile noetig
    PORTAL = "portal"             # Anzeigenportal, Anbieter gemischt
    OTHER = "sonstige"


class ListingStatus(StrEnum):
    NEW = "new"              # frisch eingesammelt
    SCORED = "scored"        # bewertet
    DISCARDED = "discarded"  # unter der Schwelle, nie gemeldet
    NOTIFIED = "notified"    # Nachricht raus, wartet auf Ja/Nein
    HANDLED = "handled"      # Entscheidung gefallen, siehe Application


class Decision(StrEnum):
    YES = "yes"
    NO = "no"
    AUTO_YES = "auto_yes"    # Timeout + Top-Score -> automatisch gesendet


class ApplicationStatus(StrEnum):
    PENDING = "pending"      # wartet auf Entscheidung
    APPROVED = "approved"    # Ja, Text wird generiert
    REJECTED = "rejected"    # Nein
    EXPIRED = "expired"      # keine Antwort, Score zu niedrig fuer Auto-Ja
    COMPOSING = "composing"  # Text wird gerade generiert
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    REPLIED = "replied"      # Vermieter hat geantwortet


class Listing(BaseModel):
    """Ein Wohnungsangebot, quellenunabhaengig normalisiert.

    Pflichtfelder sind bewusst minimal: jede Quelle liefert etwas anderes,
    und ein Adapter soll nicht an einem fehlenden Stockwerk scheitern.
    """

    source: str                      # "vonovia", "nhw", "is24", ...
    kind: Kind = Kind.OTHER          # Art des Anbieters, steuert die Farbe
    source_id: str                   # ID in der Quelle
    url: str
    title: str

    price_cold: Optional[int] = None    # Kaltmiete in Euro
    price_warm: Optional[int] = None
    sqm: Optional[float] = None
    rooms: Optional[float] = None

    street: Optional[str] = None
    zip: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    #: True = Position nur ueber den Stadtteil geschaetzt, nicht exakt.
    position_approx: bool = False

    wbs_required: Optional[bool] = None       # Wohnberechtigungsschein
    commission: Optional[bool] = None         # Provision faellig
    available_from: Optional[str] = None
    description: Optional[str] = None         # fuer die Textgenerierung wichtig
    image_url: Optional[str] = None

    # Kontaktweg - entscheidet, wie Track B bewirbt
    contact_email: Optional[str] = None
    contact_form_url: Optional[str] = None
    contact_payload: Optional[dict] = None    # quellenspezifisch, z.B. {"wrkID": ...}

    posted_at: Optional[datetime] = None
    seen_at: datetime = Field(default_factory=_now)

    status: ListingStatus = ListingStatus.NEW
    score: Optional[int] = None
    score_reasons: List[str] = Field(default_factory=list)

    @field_validator("zip")
    @classmethod
    def _clean_zip(cls, v: Optional[str]) -> str | None:
        if not v:
            return None
        m = re.search(r"\b(\d{5})\b", v)
        return m.group(1) if m else None

    @property
    def key(self) -> str:
        """Eindeutig pro Quelle. Fuer 'schon gesehen?' innerhalb einer Quelle."""
        return f"{self.source}:{self.source_id}"

    @property
    def fingerprint(self) -> str:
        """Quellenuebergreifend. Dasselbe Objekt auf IS24 und Immowelt soll
        nur einmal melden. Bewusst grob: Strasse + PLZ + gerundeter Preis.
        Lieber ein Duplikat zu viel als ein verpasstes Angebot."""
        street = re.sub(r"[^a-z0-9]", "", (self.street or "").lower())
        price_bucket = round((self.price_cold or 0) / 25)
        sqm_bucket = round((self.sqm or 0) / 5)
        raw = f"{street}|{self.zip or ''}|{price_bucket}|{sqm_bucket}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    @property
    def price_per_sqm(self) -> float | None:
        if self.price_cold and self.sqm and self.sqm > 0:
            return round(self.price_cold / self.sqm, 2)
        return None


class Application(BaseModel):
    """Eine Bewerbung auf ein Listing. Gehoert Track B."""

    id: Optional[int] = None
    listing_key: str
    status: ApplicationStatus = ApplicationStatus.PENDING

    decision: Optional[Decision] = None
    decided_at: Optional[datetime] = None

    message_text: Optional[str] = None       # der generierte Bewerbungstext
    message_model: Optional[str] = None      # welches Modell ihn geschrieben hat
    sent_via: Optional[str] = None           # "vonovia_form", "smtp", "is24_browser"
    sent_at: Optional[datetime] = None
    error: Optional[str] = None

    # ID der Messenger-Nachricht, damit eine Antwort zugeordnet werden kann
    messenger_ref: Optional[str] = None

    created_at: datetime = Field(default_factory=_now)
