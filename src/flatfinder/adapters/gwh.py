"""GWH Wohnungsgesellschaft mbH Hessen.

Die Angebote stehen NICHT im HTML von gwh.de - die Seite laedt sie per XHR
aus einem TYPO3/Solr-Endpunkt auf cms.gwh.de. Der Endpunkt selbst ist offen
und braucht keinen Browser; gefunden wurde er per Devtools-Mitschnitt:

    GET https://cms.gwh.de/rentalentities.json
        ?tx_solr[filter][9]=pid:117
        &tx_solr[filter][10]=estate_type:APARTMENT

    -> documents.list.count / .results[].content

Achtung, Falle: `overalRent` (ein l - Tippfehler der API) ist die WARMmiete.
Die Kaltmiete steht nur auf der Detailseite unter
content[0].content.rentalEntity.data.priceSet.baseRentAmount.

Weil das Scoring auf der Kaltmiete beruht, holen wir die Detailseite nach -
aber nur fuer die Objekte der gesuchten Stadt. Gemessen 2026-09-19: 123
Objekte hessenweit, davon 12 in Frankfurt. Zwoelf Extra-Requests pro
Durchlauf sind bei stuendlichem Betrieb unkritisch.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..models import Kind, Listing
from .base import HttpAdapter

log = logging.getLogger(__name__)

CMS = "https://cms.gwh.de"
SITE = "https://www.gwh.de"
LIST_URL = f"{CMS}/rentalentities.json"
LIST_PARAMS = {
    "tx_solr[filter][9]": "pid:117",
    "tx_solr[filter][10]": "estate_type:APARTMENT",
}


class GwhAdapter(HttpAdapter):
    source = "gwh"
    min_interval = 1.5

    def __init__(self, city: str = "Frankfurt am Main", client=None,
                 fetch_cold_rent: bool = True) -> None:
        super().__init__(client)
        self.city = city
        self.fetch_cold_rent = fetch_cold_rent

    async def fetch(self) -> list[Listing]:
        r = await self.get(LIST_URL, params=LIST_PARAMS,
                           headers={"Accept": "application/json"})
        payload = r.json()
        docs = (payload.get("documents") or {}).get("list") or {}
        results = docs.get("results") or []

        listings = [self.parse(d) for d in results]
        listings = [l for l in listings if l is not None]
        if self.city:
            listings = [l for l in listings
                        if self.city.lower() in (l.city or "").lower()]

        log.info("gwh: %d Objekte gesamt (API meldet %s), %d in %s",
                 len(results), docs.get("count"), len(listings), self.city or "allen Staedten")

        if self.fetch_cold_rent:
            await self._add_cold_rents(listings)
        return listings

    async def _add_cold_rents(self, listings: list[Listing]) -> None:
        """Kaltmiete von den Detailseiten nachladen. Ein Fehlschlag darf den
        ganzen Durchlauf nicht kippen - dann bleibt eben die Warmmiete."""
        for listing in listings:
            await self.polite_sleep()
            try:
                r = await self.get(f"{CMS}{_detail_path(listing)}",
                                   headers={"Accept": "application/json"})
                cold = _dig_base_rent(r.json())
                if cold is not None:
                    listing.price_cold = cold
            except Exception as e:
                log.warning("gwh: Kaltmiete fuer %s nicht ermittelbar (%s)",
                            listing.source_id, e)

    @staticmethod
    def parse(doc: dict[str, Any]) -> Listing | None:
        c = doc.get("content") or {}
        ext = c.get("externalId")
        url_path = c.get("url")
        if not ext or not url_path:
            return None

        street = " ".join(str(x) for x in (c.get("street"), c.get("houseNumber")) if x)

        return Listing(
            source="gwh",
            kind=Kind.LANDLORD,
            source_id=str(ext).replace(" ", "-").replace("/", "-"),
            url=SITE + url_path,
            title=_title(c),
            # overalRent ist die WARMmiete - die Kaltmiete kommt aus dem Detail
            price_warm=_de_euro(c.get("overalRent")),
            sqm=_de_float(c.get("overallSpace")),
            rooms=_de_float(c.get("numberOfRooms")),
            street=street or None,
            zip=str(c.get("zip")) if c.get("zip") else None,
            city=c.get("city"),
            lat=_plain_float(c.get("lat")),
            lng=_plain_float(c.get("lon")),
            available_from=c.get("availableFromDate"),
            commission=False,          # Vermieter vermietet selbst
            image_url=_first_image(c.get("media")),
            contact_form_url=SITE + url_path,
        )


def _title(c: dict[str, Any]) -> str:
    """Manche Objekte haben keinen Titel - dann steht dort die Objektnummer
    ("1600/13513/16"), was in der Liste unbrauchbar aussieht. In dem Fall
    bauen wir eine sprechende Bezeichnung aus den Eckdaten."""
    t = (c.get("title") or "").strip()
    # Ein "Titel", der nur aus Ziffern und Trennzeichen besteht, ist keiner.
    if t and not all(ch.isdigit() or ch in "/-. " for ch in t):
        return t
    zimmer = _de_float(c.get("numberOfRooms"))
    qm = _de_float(c.get("overallSpace"))
    teile = []
    if zimmer:
        teile.append(f"{zimmer:.0f}-Zimmer-Wohnung")
    else:
        teile.append("Wohnung")
    if qm:
        teile.append(f"{qm:.0f} m2")
    ort = " ".join(str(x) for x in (c.get("street"), c.get("houseNumber")) if x)
    if ort:
        teile.append(ort)
    elif c.get("city"):
        teile.append(str(c["city"]))
    return ", ".join(teile)


def _detail_path(listing: Listing) -> str:
    return listing.url[len(SITE):] if listing.url.startswith(SITE) else listing.url


def _dig_base_rent(detail: dict[str, Any]) -> int | None:
    """content[0].content.rentalEntity.data.priceSet.baseRentAmount"""
    try:
        node = detail["content"][0]["content"]["rentalEntity"]["data"]["priceSet"]
        return _de_euro(node.get("baseRentAmount"))
    except (KeyError, IndexError, TypeError):
        return None


def _de_euro(v: Any) -> int | None:
    """'1.016,00' -> 1016 (deutsches Zahlenformat)"""
    if v is None:
        return None
    s = str(v).strip().replace("\xa0", "").replace("€", "").strip()
    if not s:
        return None
    s = s.split(",")[0].replace(".", "")
    try:
        n = int(s)
    except ValueError:
        return None
    return n if n > 0 else None


def _de_float(v: Any) -> float | None:
    """'72,5' -> 72.5"""
    if v is None:
        return None
    s = str(v).strip().replace("\xa0", "").replace(".", "").replace(",", ".")
    try:
        f = float(s)
    except ValueError:
        return None
    return f if f > 0 else None


def _plain_float(v: Any) -> float | None:
    """lat/lon kommen bereits als englische Dezimalzahl."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _first_image(media: Any) -> str | None:
    if not isinstance(media, list) or not media:
        return None
    entry = media[0]
    if not isinstance(entry, dict):
        return None
    for size in ("medium", "small", "large"):
        node = entry.get(size)
        if isinstance(node, dict) and node.get("publicUrl"):
            url = node["publicUrl"]
            return url if url.startswith("http") else f"{CMS}/{url.lstrip('/')}"
    return None
