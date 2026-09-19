"""wg-gesucht.de - Wohnungen in Frankfurt.

Server-gerendertes HTML, kein Bot-Schutz auf den Listenseiten.

Wichtig zur robots.txt: gesperrt sind dort `/api/` und
`/nachricht-senden.html` - also die Kontaktstrecke. Wir LESEN nur die
Listenseiten, das ist erlaubt. Eine automatische Kontaktaufnahme ueber
diese Quelle waere ein klarer Verstoss und ist bewusst nicht gebaut.

Der angezeigte Preis ist bei wg-gesucht die GESAMTmiete (warm), nicht die
Kaltmiete. Er wird deshalb als price_warm gefuehrt; price_cold bleibt leer,
weil die Listenseite sie nicht hergibt und Raten hier schaedlich waere.

URL-Schema: /wohnungen-in-<Stadt>.<StadtID>.<Kategorie>.<Sortierung>.<Seite>.html
  Kategorie 2 = Wohnungen (1 waere WG-Zimmer, 0 alles)
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional

from selectolax.parser import HTMLParser, Node

from ..models import Kind, Listing
from .base import HttpAdapter

log = logging.getLogger(__name__)

BASE = "https://www.wg-gesucht.de"

#: Staedte-IDs von wg-gesucht. Stehen in der URL der jeweiligen Suchseite.
STADT_IDS = {
    "frankfurt am main": 41,
    "offenbach am main": 76,
    "darmstadt": 25,
    "mainz": 55,
    "wiesbaden": 96,
}

MAX_SEITEN = 3   # 28 Angebote je Seite; mehr braucht eine stuendliche Suche nicht


class WgGesuchtAdapter(HttpAdapter):
    source = "wggesucht"
    min_interval = 2.5

    def __init__(self, city: str = "Frankfurt am Main", client=None) -> None:
        super().__init__(client)
        self.city = city
        self.stadt_id = STADT_IDS.get(city.strip().lower())

    async def fetch(self) -> List[Listing]:
        if self.stadt_id is None:
            log.warning("wggesucht: keine Stadt-ID fuer %r, Adapter uebersprungen", self.city)
            return []

        raus: List[Listing] = []
        gesehen: set = set()
        for seite in range(MAX_SEITEN):
            url = (f"{BASE}/wohnungen-in-{self.city.replace(' ', '-')}"
                   f".{self.stadt_id}.2.1.{seite}.html")
            r = await self.get(url)
            teil = self.parse_page(r.text, self.city)
            # Letzte Seite erkannt, wenn nichts Neues mehr kommt.
            frisch = [l for l in teil if l.source_id not in gesehen]
            if not frisch:
                break
            gesehen.update(l.source_id for l in frisch)
            raus.extend(frisch)
            if seite + 1 < MAX_SEITEN:
                await self.polite_sleep()

        log.info("wggesucht: %d Angebote in %s", len(raus), self.city)
        return raus

    @classmethod
    def parse_page(cls, html: str, city: str) -> List[Listing]:
        tree = HTMLParser(html)
        raus: List[Listing] = []
        for node in tree.css("div.offer_list_item"):
            l = cls.parse_item(node, city)
            if l is not None:
                raus.append(l)
        return raus

    @staticmethod
    def parse_item(node: Node, city: str) -> Optional[Listing]:
        ad_id = node.attributes.get("data-id")
        if not ad_id:
            return None

        link = node.css_first("h2.truncate_title a") or node.css_first("a[href*='.html']")
        href = (link.attributes.get("href") or "") if link else ""
        if not href:
            return None
        url = href if href.startswith("http") else BASE + href

        titel = link.text(strip=True) if link else "Wohnung"
        # wg-gesucht packt die halbe Anzeige in den Titel - das ist in einer
        # Liste unlesbar. Am ersten Satzende kappen.
        titel = re.split(r"(?<=[.!?])\s", titel)[0][:110].strip() or "Wohnung"

        # "1,5-Zimmer-Wohnung | Frankfurt am Main Fechenheim | Meerholzer Straße 33"
        zimmer = stadtteil = strasse = None
        zeile = node.css_first(".col-xs-11 span")
        if zeile:
            teile = [t.strip() for t in zeile.text().split("|")]
            if teile:
                m = re.search(r"(\d+(?:[,.]\d+)?)\s*-?\s*Zimmer", teile[0])
                if m:
                    zimmer = float(m.group(1).replace(",", "."))
            if len(teile) > 1:
                ort = re.sub(r"\s+", " ", teile[1]).strip()
                if city.lower() in ort.lower():
                    rest = ort[len(city):].strip(" ,-")
                    stadtteil = rest or None
                else:
                    stadtteil = ort or None
            if len(teile) > 2:
                strasse = re.sub(r"\s+", " ", teile[2]).strip() or None

        preis = flaeche = None
        frei_ab = None
        zeile2 = node.css_first(".row.middle") or node
        for i, spalte in enumerate(zeile2.css("div[class*='col-xs-']")):
            text = spalte.text(strip=True)
            if "€" in text and preis is None:
                preis = _zahl(text)
            elif "m²" in text and flaeche is None:
                flaeche = _zahl(text, komma=True)
            elif re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", text):
                frei_ab = text

        bild = node.css_first("img.img-responsive")
        bild_url = bild.attributes.get("src") if bild else None

        return Listing(
            source="wggesucht",
            kind=Kind.PORTAL,
            source_id=str(ad_id),
            url=url,
            title=titel,
            # Der angezeigte Preis ist die Gesamtmiete, nicht die Kaltmiete.
            price_warm=preis,
            sqm=flaeche,
            rooms=zimmer,
            street=strasse,
            city=city,
            district=stadtteil,
            available_from=frei_ab,
            image_url=bild_url,
            contact_form_url=None,   # bewusst: robots.txt sperrt die Kontaktstrecke
        )


def _zahl(text: str, komma: bool = False) -> Optional[float]:
    t = text.replace("\xa0", " ").replace(".", "")
    m = re.search(r"(\d+(?:,\d+)?)", t)
    if not m:
        return None
    try:
        wert = float(m.group(1).replace(",", "."))
    except ValueError:
        return None
    if wert <= 0:
        return None
    return wert if komma else int(wert)
