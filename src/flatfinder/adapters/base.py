"""Adapter-Vertrag. Jede Quelle implementiert genau dieses Interface.

Drei Klassen von Adaptern, weil die Portale sich grundlegend unterscheiden:

  ApiAdapter      sauberer JSON-Endpunkt (Vonovia)        -> httpx, schnell
  HtmlAdapter     server-gerendertes HTML (NHW, GWH)      -> httpx + selectolax
  BrowserAdapter  Bot-Schutz, Login noetig (IS24)         -> Playwright, Heim-IP

Wer eine neue Quelle baut: von der passenden Klasse erben, `fetch()`
implementieren, Fixture-Test dazulegen. Sonst nichts.
"""

from __future__ import annotations

import abc
import asyncio
import logging
import random

import httpx

from ..models import Listing

log = logging.getLogger(__name__)

# Ehrlicher User-Agent mit Kontakt. Wir tarnen uns nicht - wenn eine Quelle
# uns nicht will, schalten wir den Adapter ab, statt ihn zu verstecken.
UA = "flatfinder-ffm/0.1 (privater Wohnungssuch-Bot; +kontakt@example.org)"


class AdapterError(RuntimeError):
    pass


class Blocked(AdapterError):
    """Quelle hat uns gesperrt. Adapter deaktivieren, nicht umgehen."""


class Adapter(abc.ABC):
    source: str
    #: True = braucht eine private IP. Kleinanzeigen und IS24 sperren
    #: Rechenzentrums-IPs pauschal (gemessen: 403 bzw. 401).
    requires_residential_ip: bool = False
    #: Sekunden zwischen zwei Requests an denselben Host.
    min_interval: float = 1.0
    enabled: bool = True

    @abc.abstractmethod
    async def fetch(self) -> list[Listing]:
        """Aktuelle Angebote holen. Wirft Blocked, wenn die Quelle dichtmacht."""

    async def polite_sleep(self) -> None:
        """Jitter, damit wir kein Metronom sind."""
        await asyncio.sleep(self.min_interval * random.uniform(0.8, 1.6))


class HttpAdapter(Adapter):
    """Basis fuer alles, was ueber httpx laeuft."""

    base_url: str = ""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self):
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={"User-Agent": UA, "Accept-Language": "de-DE,de;q=0.9"},
                timeout=httpx.Timeout(20.0),
                follow_redirects=True,
            )
        return self

    async def __aexit__(self, *exc) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise AdapterError(f"{self.source}: benutze 'async with', Client fehlt")
        return self._client

    async def get(self, url: str, **kw) -> httpx.Response:
        r = await self.client.get(url, **kw)
        if r.status_code in (401, 403, 429):
            raise Blocked(f"{self.source}: HTTP {r.status_code} auf {url}")
        r.raise_for_status()
        return r


class BrowserAdapter(Adapter):
    """Basis fuer Playwright-Quellen (IS24).

    Laeuft NUR auf dem Heim-Node - vom Rechenzentrum kommt 401. Nutzt ein
    persistentes Profil mit echtem Login, kein anonymes Crawling.

    Bewusst NICHT enthalten: Captcha-Loeser und Proxy-Rotation. Begegnet uns
    ein Captcha, endet der Lauf mit Blocked. Siehe DECISIONS.md.
    """

    requires_residential_ip = True
    min_interval = 8.0
    profile_dir: str = "playwright-profile"
