"""Versand der Bewerbung. Ein Sender pro Kontaktweg.

DRY_RUN=true (Standard) protokolliert nur und verschickt nichts. Erst
umstellen, wenn du zehn generierte Texte gelesen und fuer gut befunden hast.
Ein falsch adressierter Bot, der 200 Vermieter anschreibt, ist nicht
zurueckholbar.
"""

from __future__ import annotations

import logging
import smtplib
from typing import TYPE_CHECKING
from email.message import EmailMessage

import httpx

from ..config import Profile, Settings
from ..models import Listing
if TYPE_CHECKING:
    from .compose import Bewerbung

log = logging.getLogger(__name__)


class SendError(RuntimeError):
    pass


async def send(listing: Listing, text: "Bewerbung", s: Settings, p: Profile) -> str:
    """Waehlt den Kontaktweg. Gibt zurueck, worueber gesendet wurde."""
    if s.dry_run:
        log.warning("DRY_RUN - nichts versendet. Text waere gewesen:\n%s\n%s",
                    text.subject, text.body)
        return "dry_run"

    if listing.contact_form_url and listing.source == "vonovia":
        await _vonovia_form(listing, text, p)
        return "vonovia_form"
    if listing.contact_email:
        _smtp(listing, text, s, p)
        return "smtp"
    raise SendError(f"{listing.key}: kein Kontaktweg bekannt")


async def _vonovia_form(listing: Listing, text: "Bewerbung", p: Profile) -> None:
    """Vonovia nimmt die Kontaktanfrage als schlichten POST entgegen -
    kein Browser noetig. Feldnamen stammen aus dem Frontend-Formular
    (real-estate-contact-form).
    """
    payload = {
        **(listing.contact_payload or {}),
        "salutation": "",
        "firstname": p.full_name.split(" ")[0] if p.full_name else "",
        "lastname": " ".join(p.full_name.split(" ")[1:]) if p.full_name else "",
        "email": p.email,
        "phone": p.phone,
        "your_message": text.body,
    }
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
        r = await c.post(listing.contact_form_url, data=payload)
        if r.status_code >= 400:
            raise SendError(f"Vonovia-Formular {r.status_code}: {r.text[:300]}")
    log.info("Bewerbung an Vonovia gesendet: %s", listing.key)


def _smtp(listing: Listing, text: "Bewerbung", s: Settings, p: Profile) -> None:
    if not s.smtp_host:
        raise SendError("SMTP nicht konfiguriert")
    msg = EmailMessage()
    msg["Subject"] = text.subject
    msg["From"] = p.email
    msg["To"] = listing.contact_email
    msg.set_content(text.body)
    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=30) as srv:
            srv.starttls()
            if s.smtp_user:
                srv.login(s.smtp_user, s.smtp_password)
            srv.send_message(msg)
    except OSError as e:
        raise SendError(f"SMTP: {e}") from e
    log.info("Bewerbung per Mail gesendet: %s -> %s", listing.key, listing.contact_email)
