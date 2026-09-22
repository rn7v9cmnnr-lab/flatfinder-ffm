"""Public ohne-makler.net cards and labeled prices from detail pages."""
from __future__ import annotations
import re
import logging
import httpx
from urllib.parse import urljoin
from selectolax.parser import HTMLParser
from ..models import Kind, Listing
from .base import HttpAdapter, AdapterError

def number(text):
    m = re.search(r"[0-9]+(?:\.[0-9]{3})*(?:,[0-9]+)?", text or "")
    return float(m.group().replace(".", "").replace(",", ".")) if m else None

BASE = "https://www.ohne-makler.net"
SEARCH = BASE + "/immobilien/wohnung-mieten/hessen/frankfurt-main/"

class OhneMaklerAdapter(HttpAdapter):
    source = "ohnemakler"
    min_interval = 1.5

    async def fetch(self):
        found = {}
        for page in range(1, 4):
            if page > 1:
                await self.polite_sleep()
            r = await self.get(SEARCH, params={"page": page})
            tree = HTMLParser(r.text)
            if not tree.css("a[data-om-id]"):
                raise AdapterError("ohne-makler: Angebotsstruktur fehlt")
            items = self.parse_page(r.text)
            old = len(found)
            found.update({l.key: l for l in items})
            if old == len(found):
                break
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
        out = {}
        for node in HTMLParser(html).css('a[data-om-id][data-om-type="RENT"]'):
            title = node.css_first("h4")
            address = next((n.text(separator=" ", strip=True) for n in node.css("span")
                            if re.match(r"^\d{5}\s+Frankfurt", n.text(strip=True))), "")
            if title is None or not address:
                continue  # Search also returns surrounding towns: do not relabel them Frankfurt.
            district = re.search(r"\(([^)]+)\)\s*$", address)
            sqm = node.css_first('[title="Wohnfläche"]')
            rooms = node.css_first('[title="Zimmer"]')
            img = node.css_first("img[src]")
            l = Listing(source="ohnemakler", source_id=node.attributes["data-om-id"],
                kind=Kind.PORTAL, title=title.text(strip=True), city="Frankfurt am Main",
                zip=address[:5], district=district[1] if district else None,
                url=urljoin(BASE, node.attributes["href"]),
                sqm=number(sqm.text()) if sqm else None, rooms=number(rooms.text()) if rooms else None,
                image_url=img.attributes["src"] if img else None, commission=False)
            out[l.key] = l
        return list(out.values())

    @staticmethod
    def enrich(listing, html):
        for row in HTMLParser(html).css("tr"):
            cells = row.css("td")
            if len(cells) < 2:
                continue
            label, value = cells[0].text(strip=True).lower(), cells[1].text(strip=True)
            if label in ("kaltmiete", "nettokaltmiete", "warmmiete") and number(value) is not None:
                setattr(listing, "price_warm" if label == "warmmiete" else "price_cold", round(number(value)))
