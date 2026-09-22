"""Public Kleinanzeigen search, no login or challenge bypass. Two newest pages."""
from __future__ import annotations
import re
import logging
import httpx
from urllib.parse import urljoin
from selectolax.parser import HTMLParser
from ..models import Kind, Listing
from .base import HttpAdapter, AdapterError

BASE = "https://www.kleinanzeigen.de"
SEARCH = BASE + "/s-wohnung-mieten/frankfurt-am-main/anzeige:angebote/{page}c203l4292"

def number(text):
    m = re.search(r"[0-9]+(?:\.[0-9]{3})*(?:,[0-9]+)?", text or "")
    return float(m.group().replace(".", "").replace(",", ".")) if m else None

class KleinanzeigenAdapter(HttpAdapter):
    source = "kleinanzeigen"
    min_interval = 1.5

    async def fetch(self):
        found = {}
        for page in range(1, 3):
            if page > 1:
                await self.polite_sleep()
            response = await self.get(SEARCH.format(page="" if page == 1 else f"seite:{page}/"))
            items = self.parse_page(response.text)
            if not items:
                raise AdapterError("Kleinanzeigen: keine lesbaren Angebotskarten")
            found.update({l.key: l for l in items})
        for listing in found.values():
            await self.polite_sleep()
            try:
                r = await self.get(listing.url)
                self.enrich(listing, r.text)
            except httpx.HTTPError as exc:
                logging.getLogger(__name__).warning("Detail nicht erreichbar: %s (%s)", listing.url, type(exc).__name__)
        return list(found.values())

    @staticmethod
    def parse_page(html):
        tree = HTMLParser(html)
        out = {}
        for node in tree.css("article[data-adid]"):
            title = node.css_first("h3 a, h2 a")
            if title is None:
                continue
            href = title.attributes.get("href", "")
            if not re.search(r"/s-anzeige/.+/[0-9]+-203-", href):
                continue
            # Strip embedded JSON so descriptions/images cannot pollute location/facts.
            for script in node.css("script"):
                script.decompose()
            location = next((n.text(strip=True) for n in node.css("span")
                             if re.match(r"^(60[0-9]{3}|659[0-9]{2})\s", n.text(strip=True))), "")
            if not location:
                continue
            facts = " ".join(n.text(separator=" ", strip=True) for n in node.css("p"))
            sqm = re.search(r"([0-9.,]+)\s*m²", facts)
            rooms = re.search(r"([0-9.,]+)\s*Zi\.", facts)
            img = node.css_first("img[src]")
            listing = Listing(source="kleinanzeigen", kind=Kind.PORTAL,
                source_id=node.attributes["data-adid"], title=title.text(strip=True),
                url=urljoin(BASE, href), city="Frankfurt am Main", zip=location[:5],
                district=location[5:].strip(), sqm=number(sqm[1]) if sqm else None,
                rooms=number(rooms[1]) if rooms else None,
                image_url=img.attributes.get("src") if img else None)
            out[listing.key] = listing
        return list(out.values())

    @staticmethod
    def enrich(listing, html):
        tree = HTMLParser(html)
        description = tree.css_first("#viewad-description-text")
        text = description.text(separator=" ", strip=True) if description else ""
        # An unlabeled headline price is deliberately NOT guessed to be cold rent.
        for attr, label in [("price_cold", r"(?:Netto)?kaltmiete"), ("price_warm", r"Warmmiete")]:
            m = re.search(label + r"\s*[:=]?\s*([0-9.,]+)\s*(?:€|Euro)", text, re.I)
            if m:
                setattr(listing, attr, round(number(m[1])))
        if listing.price_warm is None:
            m = re.search(r"([0-9.,]+)\s*(?:€|Euro)\s*warm\b", listing.title, re.I)
            if m:
                listing.price_warm = round(number(m[1]))
        for node in tree.css(".addetailslist--detail"):
            value = node.css_first(".addetailslist--detail--value")
            if value is not None and "Verfügbar ab" in node.text():
                listing.available_from = value.text(strip=True)
        listing.description = text[:1500] or None
