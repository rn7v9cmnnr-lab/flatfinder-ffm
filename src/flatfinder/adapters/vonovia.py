"""Vonovia - die beste Quelle fuer Frankfurt.

Echte JSON-API, kein Bot-Schutz, funktioniert vom Rechenzentrum. Der Flow ist
der, den das Frontend selbst benutzt:

    GET  /api/real-estate/search-token           -> {"token": ..., "ttl": 900}
    GET  /api/real-estate/list?city=...&offset=N Header: X-VON-Search-Token
    POST /api/real-estate/{wrk_id}/contact-form  Feld: wrkID

Paging laeuft ueber `offset`, die Seitengroesse ist fest 15. `limit` darf man
NICHT setzen - die API antwortet dann mit einer Fehlerseite statt JSON.

Gemessen am 2026-09-19: 56 Objekte fuer Frankfurt am Main, Antwort in <1s.
Viele davon sind Garagen und Stellplaetze - deshalb filtert `_is_flat()`.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from ..models import Kind, Listing
from .base import AdapterError, HttpAdapter

log = logging.getLogger(__name__)

BASE = "https://www.vonovia.de"
TOKEN_URL = f"{BASE}/api/real-estate/search-token"
LIST_URL = f"{BASE}/api/real-estate/list"
EXPOSE_URL = f"{BASE}/immobilien/{{slug}}"

PAGE_SIZE = 15      # von der API vorgegeben, nicht aenderbar
MAX_OFFSET = 500    # Notbremse, falls die API offset ignoriert

# Vonovia mischt alles in einen Endpunkt. Ohne diese Liste rutschen Garagen
# und Gewerbeflaechen als "Wohnung" durch - gesehen am 2026-09-19 bei einer
# 116 m2 "Einzelhandels-/Buero-/Praxisflaeche" mit anzahl_zimmer=1.
NICHT_WOHNUNG = (
    "garage", "stellplatz", "parken", "tiefgarage", "carport",
    "gewerbe", "buero", "büro", "praxis", "einzelhandel", "laden",
    "lager", "halle", "ladenlokal", "gastronomie",
)


class VonoviaAdapter(HttpAdapter):
    source = "vonovia"
    min_interval = 2.0

    def __init__(self, city: str = "Frankfurt am Main", client=None) -> None:
        super().__init__(client)
        self.city = city
        self._token: str | None = None
        self._token_expires: float = 0.0

    async def _get_token(self) -> str:
        """Token ist 900s gueltig. Wir erneuern 60s vor Ablauf."""
        if self._token and time.monotonic() < self._token_expires - 60:
            return self._token
        r = await self.get(TOKEN_URL, headers={"Accept": "application/json"})
        data = r.json()
        token = data.get("token")
        if not token:
            raise AdapterError(f"vonovia: kein Token in Antwort: {data!r}")
        self._token = token
        self._token_expires = time.monotonic() + float(data.get("ttl", 900))
        return token

    async def _page(self, offset: int) -> dict[str, Any]:
        token = await self._get_token()
        r = await self.get(
            LIST_URL,
            params={"city": self.city, "offset": offset},
            headers={"Accept": "application/json", "X-VON-Search-Token": token},
        )
        return r.json()

    async def fetch(self) -> list[Listing]:
        raw: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        offset = 0
        total: int | None = None

        while offset < MAX_OFFSET:
            payload = await self._page(offset)
            batch = payload.get("results") or []
            if not batch:
                if offset == 0:
                    # Frankfurt hat immer Objekte. Eine leere erste Seite
                    # heisst: die API hat gehustet, nicht "nichts da". Das
                    # als Ergebnis durchzureichen hat am 2026-09-21 dazu
                    # gefuehrt, dass 15 vorhandene Wohnungen als
                    # verschwunden in der Liste standen.
                    raise AdapterError(
                        f"vonovia: erste Seite leer (Antwort: {str(payload)[:120]})")
                break
            info = (payload.get("paging") or {}).get("info") or {}
            total = total or _to_int(info.get("count"))

            # Schutz gegen eine API, die offset ignoriert: waere jede Seite
            # identisch, liefen wir sonst bis MAX_OFFSET durch.
            fresh = [i for i in batch if str(i.get("wrk_id")) not in seen_ids]
            if not fresh:
                break
            seen_ids.update(str(i.get("wrk_id")) for i in fresh)
            raw.extend(fresh)

            offset += PAGE_SIZE
            if total is not None and offset >= total:
                break
            await self.polite_sleep()

        flats = [self.parse(i) for i in raw if _is_flat(i)]
        log.info("vonovia: %d Objekte geholt (API meldet %s), davon %d Wohnungen",
                 len(raw), total, len(flats))
        return flats

    @staticmethod
    def parse(item: dict[str, Any]) -> Listing:
        """Rohes API-Objekt -> Listing. Statisch, damit Tests ohne Netz laufen."""
        wrk_id = str(item.get("wrk_id", ""))
        slug = item.get("slug") or wrk_id
        ort = item.get("ort") or ""
        # "Frankfurt am Main OT Schwanheim" -> Stadtteil rausziehen
        district = None
        if " OT " in ort:
            ort, district = (p.strip() for p in ort.split(" OT ", 1))

        return Listing(
            source="vonovia",
            kind=Kind.LANDLORD,
            source_id=wrk_id,
            url=EXPOSE_URL.format(slug=slug),
            title=item.get("titel") or "Wohnung",
            price_cold=_to_int(item.get("preis")),
            sqm=_to_float(item.get("groesse")),
            rooms=_to_float(item.get("anzahl_zimmer")),
            street=(item.get("strasse") or "").strip() or None,
            zip=item.get("plz"),
            city=ort or None,
            district=district,
            lat=_to_float(item.get("lat")),
            lng=_to_float(item.get("lng")),
            commission=False,  # Vermieter vermietet selbst, nie Provision
            image_url=item.get("preview_img_url") or None,
            contact_form_url=f"{BASE}/api/real-estate/{wrk_id}/contact-form",
            contact_payload={"wrkID": wrk_id},
        )


def _is_flat(item: dict[str, Any]) -> bool:
    """Garagen, Stellplaetze und Gewerbe aussortieren.

    Vonovia mischt alles in einen Endpunkt. Kriterium: zur Miete, hat Flaeche
    und mindestens ein Zimmer. Eine Garage hat groesse=0 und zimmer=0.
    """
    if str(item.get("vermarktungsart_miete")) != "1":
        return False
    if _to_float(item.get("groesse")) in (None, 0.0):
        return False
    if (_to_float(item.get("anzahl_zimmer")) or 0) < 1:
        return False
    title = (item.get("titel") or "").lower()
    if any(w in title for w in NICHT_WOHNUNG):
        return False
    return True


def _to_int(v: Any) -> int | None:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _to_float(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
