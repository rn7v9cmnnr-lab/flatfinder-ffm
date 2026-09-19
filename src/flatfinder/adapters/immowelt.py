"""Immowelt - braucht einen echten Browser.

Die Angebote stehen nicht im HTML, die Seite baut sie per JavaScript auf.
Ausserdem laeuft davor DataDome, ein aktiver Bot-Schutz.

Damit ist diese Quelle die unzuverlaessigste im Projekt: mal laesst sie uns
durch, mal nicht - und auf einem GitHub-Runner (Rechenzentrums-IP) eher
nicht. Genau deshalb meldet der Adapter bei einer Sperre `Blocked` und wird
abgeschaltet, statt sich zu tarnen. Kein Captcha-Loeser, keine
Proxy-Rotation: das waere Umgehen einer Schutzmassnahme, nicht mehr
Automatisierung.

Playwright ist eine optionale Abhaengigkeit:  pip install -e ".[browser]"
Fehlt es, meldet der Adapter das und wird uebersprungen.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional

from ..models import Kind, Listing
from .base import Adapter, Blocked

log = logging.getLogger(__name__)

BASE = "https://www.immowelt.de"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")

#: Karten dieser Art sind keine Mietwohnungen fuer uns.
UNERWUENSCHT = ("wg-zimmer", "zimmer zur miete", "haus zur miete",
                "stellplatz", "garage", "gewerbe", "buero")

#: Hinweise darauf, dass der Bot-Schutz zugeschlagen hat.
SPERRE = ("ich bin kein roboter", "captcha", "zugriff verweigert",
          "access denied", "unusual traffic")

# Das JS laeuft im Browser und liefert je Angebot den Kartentext.
KARTEN_JS = """() => {
  const seen = new Set(); const out = [];
  for (const a of document.querySelectorAll("a[href*='/expose/']")) {
    const href = a.href.split('?')[0];
    const id = href.split('/expose/')[1];
    if (!id || seen.has(id)) continue;
    let n = a, box = null;
    for (let i = 0; i < 8 && n; i++, n = n.parentElement) {
      const t = n.innerText || '';
      if (t.includes('\\u20ac') && t.includes('m\\u00b2')) { box = n; break; }
    }
    if (!box) continue;
    seen.add(id);
    const img = box.querySelector('img');
    out.push({ id, href, text: box.innerText, img: img ? img.src : null });
  }
  return out;
}"""


class ImmoweltAdapter(Adapter):
    source = "immowelt"
    min_interval = 6.0

    def __init__(self, city: str = "Frankfurt am Main") -> None:
        self.city = city

    @property
    def _url(self) -> str:
        slug = self.city.lower().replace(" ", "-").replace("ü", "ue").replace("ö", "oe")
        return f"{BASE}/liste/{slug}/wohnungen/mieten"

    async def fetch(self) -> List[Listing]:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            log.warning('immowelt: Playwright fehlt (pip install -e ".[browser]") - uebersprungen')
            return []

        # Umgebungen mit eigenem Browser oder eigener CA (z.B. hinter einem
        # Proxy) koennen das ueber Umgebungsvariablen steuern, statt dass wir
        # hier Annahmen ueber den Rechner treffen.
        start: Dict[str, Any] = {}
        pfad = os.environ.get("PLAYWRIGHT_EXECUTABLE_PATH")
        if pfad:
            start["executable_path"] = pfad
        # Getrennt mit "|", nicht mit Komma: Chromium-Argumente wie
        # --ignore-certificate-errors-spki-list enthalten selbst Kommas,
        # und ein zerlegter Wert sieht fuer Playwright aus wie eine URL
        # ("Arguments can not specify page to be opened").
        extra = os.environ.get("PLAYWRIGHT_ARGS")
        if extra:
            start["args"] = [a for a in extra.split("|") if a.strip()]

        rohkarten: List[Dict[str, Any]] = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(**start)
            try:
                ctx = await browser.new_context(user_agent=UA, locale="de-DE",
                                                viewport={"width": 1280, "height": 900})
                page = await ctx.new_page()
                antwort = await page.goto(self._url, wait_until="domcontentloaded",
                                          timeout=45000)
                await page.wait_for_timeout(5000)

                status = antwort.status if antwort else 0
                titel = (await page.title() or "").lower()
                text = ((await page.inner_text("body"))[:1500] or "").lower()
                if status in (401, 403, 429) or any(w in titel + text for w in SPERRE):
                    raise Blocked(f"immowelt: Bot-Schutz (HTTP {status}, Titel {titel[:40]!r})")

                rohkarten = await page.evaluate(KARTEN_JS)
            finally:
                await browser.close()

        listings = [self.parse(k, self.city) for k in rohkarten]
        listings = [l for l in listings if l is not None]
        log.info("immowelt: %d Karten, davon %d Mietwohnungen", len(rohkarten), len(listings))
        return listings

    @staticmethod
    def parse(karte: Dict[str, Any], city: str) -> Optional[Listing]:
        text = karte.get("text") or ""
        niedrig = text.lower()
        if any(w in niedrig for w in UNERWUENSCHT):
            return None

        zeilen = [z.strip() for z in text.split("\n") if z.strip() and z.strip() != "·"]

        preis = None
        warm = False
        for i, z in enumerate(zeilen):
            if "€" in z:
                preis = _euro(z)
                # Direkt darunter steht, ob es Kalt- oder Warmmiete ist.
                label = zeilen[i + 1].lower() if i + 1 < len(zeilen) else ""
                warm = "warm" in label or "gesamt" in label
                break

        qm = zimmer = None
        for z in zeilen:
            if qm is None and "m²" in z:
                qm = _dez(z)
            if zimmer is None and "zimmer" in z.lower():
                zimmer = _dez(z)

        # Letzte Zeile: "Feuerbachstraße, Westend-Süd, Frankfurt am Main (60325)"
        strasse = stadtteil = plz = None
        for z in reversed(zeilen):
            if city.lower() in z.lower() or re.search(r"\(\d{5}\)", z):
                m = re.search(r"\((\d{5})\)", z)
                plz = m.group(1) if m else None
                teile = [t.strip() for t in re.sub(r"\(\d{5}\)", "", z).split(",") if t.strip()]
                teile = [t for t in teile if city.lower() not in t.lower()]
                if teile:
                    strasse = teile[0]
                if len(teile) > 1:
                    stadtteil = teile[-1]
                break

        frei_ab = next((z.replace("frei ab", "").strip()
                        for z in zeilen if z.lower().startswith("frei ab")), None)

        titel = next((z for z in zeilen if "zur miete" in z.lower()), "Wohnung")

        return Listing(
            source="immowelt",
            kind=Kind.PORTAL,
            source_id=str(karte.get("id", ""))[:40],
            url=karte.get("href") or BASE,
            title=titel,
            price_cold=None if warm else preis,
            price_warm=preis if warm else None,
            sqm=qm,
            rooms=zimmer,
            street=strasse,
            zip=plz,
            city=city,
            district=stadtteil,
            available_from=frei_ab,
            image_url=karte.get("img"),
            # robots.txt sperrt bei Immowelt ausdruecklich die Kontaktstrecke
            # (GetAnbieterKontaktanfrageForm, kontaktanfragegesendet).
            contact_form_url=None,
        )


def _euro(text: str) -> Optional[int]:
    m = re.search(r"([\d.]+)(?:,\d+)?\s*€", text.replace("\xa0", " "))
    if not m:
        return None
    try:
        wert = int(m.group(1).replace(".", ""))
    except ValueError:
        return None
    return wert if wert > 0 else None


def _dez(text: str) -> Optional[float]:
    m = re.search(r"(\d+(?:[,.]\d+)?)", text.replace("\xa0", " "))
    if not m:
        return None
    try:
        wert = float(m.group(1).replace(",", "."))
    except ValueError:
        return None
    return wert if wert > 0 else None
