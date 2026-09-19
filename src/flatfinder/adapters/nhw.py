"""Nassauische Heimstaette / Wohnstadt (naheimst.de).

Grosser hessischer Wohnungsanbieter, server-gerendertes HTML, kein Bot-Schutz.
Die Uebersichtsseite listet ganz Hessen auf einer Seite - kein Paging noetig,
aber wir filtern auf die gesuchte Stadt.

Gemessen 2026-09-19: 67 Angebote gesamt, davon 15 in Frankfurt am Main.

Geparst wird ueber die Fact-LABELS ("Wohnflaeche", "Zimmer",
"Nettokaltmiete"), nicht ueber die Reihenfolge - fuenf Angebote haben keinen
Preis, und die Etage steht mal vor, mal hinter der Miete.

WBS: steht nicht in der Uebersicht, nur auf der Detailseite. Bleibt hier
None; bei einem oeffentlichen Anbieter ist WBS-Pflicht haeufig, also im
Zweifel selbst nachsehen.
"""

from __future__ import annotations

import logging
import re

from selectolax.parser import HTMLParser, Node

from ..models import Listing
from .base import HttpAdapter

log = logging.getLogger(__name__)

BASE = "https://www.naheimst.de"
LIST_URL = f"{BASE}/wohnungsangebote"


class NhwAdapter(HttpAdapter):
    source = "nhw"
    min_interval = 3.0

    def __init__(self, city: str = "Frankfurt am Main", client=None) -> None:
        super().__init__(client)
        self.city = city

    async def fetch(self) -> list[Listing]:
        r = await self.get(LIST_URL)
        listings = self.parse_page(r.text, self.city)
        log.info("nhw: %d Angebote in %s", len(listings), self.city)
        return listings

    @classmethod
    def parse_page(cls, html: str, city: str) -> list[Listing]:
        tree = HTMLParser(html)
        out: list[Listing] = []
        for node in tree.css("div.immo--item"):
            listing = cls.parse_item(node)
            if listing is None:
                continue
            # NHW listet ganz Hessen - nur die gesuchte Stadt behalten.
            if city.lower() not in (listing.city or "").lower():
                continue
            out.append(listing)
        return out

    @staticmethod
    def parse_item(node: Node) -> Listing | None:
        # Reihenfolge ist wichtig: selectolax wertet Komma-Selektoren von
        # links nach rechts aus, nicht in Dokumentreihenfolge. Ohne diese
        # Prioritaet gewinnt der "Jetzt anfragen"-Link und wir landen auf
        # der Detailseite mit #request statt auf der Detailseite selbst.
        href = ""
        for sel in ("span.immo--item--title a",
                    ".immo--item--image--wrap a",
                    "a[href*='/immobilie/']"):
            link = node.css_first(sel)
            if link is not None and link.attributes.get("href"):
                href = link.attributes["href"]
                break
        if not href:
            return None
        href = href.split("#", 1)[0]          # Fragment gehoert nicht in die URL
        url = href if href.startswith("http") else BASE + href

        # Objektnummer aus der URL ist stabiler als die interne data-itemuid,
        # die sich bei jedem Seitenaufbau aendern kann.
        m = re.search(r"/immobilie/([^?#]+)", href)
        source_id = m.group(1) if m else (node.attributes.get("data-itemuid") or url)

        title_node = node.css_first("span.immo--item--title a, .immo--item--title")
        title = title_node.text(strip=True) if title_node else "Wohnung"

        # Stadt steht als Tag im Bild-Overlay, Adresse in der Location-Zeile.
        city = None
        for tag in node.css("span.tag"):
            t = tag.text(strip=True)
            if t and t.lower() != "neu":
                city = t
                break

        street = None
        loc = node.css_first(".immo--item--location")
        if loc:
            text = loc.text(strip=True)
            # "Offenbach am Main, Kettelerstraße 44"
            if "," in text:
                ort, _, rest = text.partition(",")
                city = city or ort.strip()
                street = rest.strip() or None
            else:
                street = text or None

        facts = _facts(node)

        return Listing(
            source="nhw",
            source_id=source_id,
            url=url,
            title=title,
            price_cold=_euro(facts.get("nettokaltmiete")),
            sqm=_qm(facts.get("wohnfläche")),
            rooms=_num(facts.get("zimmer")),
            street=street,
            city=city,
            commission=False,   # Vermieter vermietet selbst
            image_url=_img(node),
            contact_form_url=url + "#request",
        )


def _facts(node: Node) -> dict[str, str]:
    """Label -> Wert. Robust gegen Reihenfolge und fehlende Felder."""
    out: dict[str, str] = {}
    for fact in node.css(".immo--item--fact"):
        label = fact.css_first(".immo--item--fact--label")
        value = fact.css_first(".immo--item--fact--value")
        if label and value:
            out[label.text(strip=True).lower()] = value.text(strip=True)
    return out


def _img(node: Node) -> str | None:
    img = node.css_first("img.immo--item--image")
    if img is None:
        return None
    src = img.attributes.get("src")
    if not src:
        return None
    return src if src.startswith("http") else BASE + src


def _euro(v: str | None) -> int | None:
    """'533,00 €' -> 533"""
    if not v:
        return None
    m = re.search(r"([\d.]+)(?:,(\d{2}))?", v.replace("\xa0", " "))
    if not m:
        return None
    try:
        return int(m.group(1).replace(".", ""))
    except ValueError:
        return None


def _qm(v: str | None) -> float | None:
    """'53,17 m²' -> 53.17"""
    if not v:
        return None
    m = re.search(r"([\d.]+,?\d*)", v.replace("\xa0", " "))
    if not m:
        return None
    try:
        return float(m.group(1).replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _num(v: str | None) -> float | None:
    if not v:
        return None
    m = re.search(r"(\d+(?:[,.]\d+)?)", v)
    return float(m.group(1).replace(",", ".")) if m else None
