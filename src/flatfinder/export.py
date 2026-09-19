"""Erzeugt die Datendatei fuer die Weboberflaeche.

Laeuft stuendlich als GitHub Action, schreibt site/data/listings.json und
committet sie. GitHub Pages liefert die Seite aus - es laeuft also kein
Server und kein Rechner von uns.

Warum eine JSON-Datei statt einer Datenbank: ein Action-Lauf startet jedes
Mal in einem frischen Container, eine lokale SQLite waere danach weg.
Die vorherige JSON-Datei ist unser Gedaechtnis - daraus uebernehmen wir,
wann ein Angebot zum ersten Mal auftauchte ("neu"-Markierung), und wie
lange wir es schon nicht mehr gesehen haben.

Gefiltert wird hier NICHT. Die Oberflaeche bekommt alles Gefundene und
filtert im Browser - so wirken Filteraenderungen sofort, ohne neuen Lauf.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

from .adapters.base import Adapter, Blocked
from .adapters.gwh import GwhAdapter
from .adapters.immowelt import ImmoweltAdapter
from .adapters.nhw import NhwAdapter
from .adapters.vonovia import VonoviaAdapter
from .adapters.wggesucht import WgGesuchtAdapter
from .bezirke import finde as bezirk_finden
from .config import Criteria
from .models import Listing
from .scoring import score as score_listing

log = logging.getLogger(__name__)

#: Wie lange ein verschwundenes Angebot noch angezeigt wird, bevor es
#: aus der Datei faellt. Kurz genug, dass die Liste nicht vermuellt;
#: lang genug, dass ein Aussetzer einer Quelle nichts loescht.
BEHALTEN_TAGE = 14


def adapters_for(criteria: Criteria) -> List[Adapter]:
    return [
        # Grossvermieter: offene Schnittstellen, zuverlaessig
        VonoviaAdapter(criteria.city),
        NhwAdapter(criteria.city),
        GwhAdapter(criteria.city),
        # Portale
        WgGesuchtAdapter(criteria.city),
        # Braucht einen Browser und faellt bei Bot-Schutz sauber aus
        ImmoweltAdapter(criteria.city),
    ]


async def collect(criteria: Criteria) -> tuple[List[Listing], Dict[str, str]]:
    """Alle Quellen abfragen. Eine kaputte Quelle darf die anderen nicht
    mitreissen - lieber eine unvollstaendige Liste als gar keine."""
    gefunden: List[Listing] = []
    status: Dict[str, str] = {}

    for adapter in adapters_for(criteria):
        try:
            listings = await adapter.fetch()
        except Blocked as e:
            log.error("%s gesperrt: %s", adapter.source, e)
            status[adapter.source] = "gesperrt"
            continue
        except Exception as e:
            log.exception("%s fehlgeschlagen", adapter.source)
            status[adapter.source] = f"Fehler: {type(e).__name__}"
            continue
        finally:
            close = getattr(adapter, "aclose", None)
            if close:
                await close()

        for l in listings:
            # Portale liefern keine Koordinaten. Ohne Naeherung waere der
            # Umkreisfilter fuer sie wirkungslos - also den Stadtteilmittel-
            # punkt nehmen und das ehrlich kennzeichnen.
            if l.lat is None or l.lng is None:
                pos = bezirk_finden(l.district)
                if pos:
                    l.lat, l.lng = pos
                    l.position_approx = True
            l.score, l.score_reasons = score_listing(l, criteria)
        gefunden.extend(listings)
        status[adapter.source] = f"{len(listings)} Angebote"
        log.info("%s: %d Angebote", adapter.source, len(listings))

    return gefunden, status


def merge(neu: List[Listing], alt_pfad: Path) -> List[Dict[str, Any]]:
    """Neue Funde mit dem letzten Stand zusammenfuehren.

    Erhaelt `first_seen` (sonst waere nach jedem Lauf alles "neu") und
    behaelt kurzzeitig verschwundene Angebote, damit ein Aussetzer einer
    Quelle die Liste nicht leerraeumt.
    """
    jetzt = datetime.now(timezone.utc)
    vorher: Dict[str, Dict[str, Any]] = {}
    if alt_pfad.exists():
        try:
            vorher = {e["key"]: e for e in json.loads(alt_pfad.read_text())["listings"]}
        except (KeyError, ValueError, TypeError) as e:
            log.warning("Alte Datei unlesbar, fange neu an: %s", e)

    raus: Dict[str, Dict[str, Any]] = {}
    for l in neu:
        frueher = vorher.get(l.key)
        eintrag = _to_dict(l)
        eintrag["first_seen"] = (frueher or {}).get("first_seen") or jetzt.isoformat()
        eintrag["last_seen"] = jetzt.isoformat()
        eintrag["gone"] = False
        raus[l.key] = eintrag

    # Was diesmal fehlte: markieren statt sofort loeschen.
    grenze = jetzt - timedelta(days=BEHALTEN_TAGE)
    for key, alt in vorher.items():
        if key in raus:
            continue
        try:
            zuletzt = datetime.fromisoformat(alt.get("last_seen", ""))
        except ValueError:
            continue
        if zuletzt > grenze:
            alt["gone"] = True
            raus[key] = alt

    return sorted(raus.values(), key=lambda e: (-(e.get("score") or 0), e.get("key", "")))


def _to_dict(l: Listing) -> Dict[str, Any]:
    return {
        "key": l.key,
        "source": l.source,
        "kind": str(l.kind),
        "url": l.url,
        "title": l.title,
        "price_cold": l.price_cold,
        "price_warm": l.price_warm,
        "price_per_sqm": l.price_per_sqm,
        "sqm": l.sqm,
        "rooms": l.rooms,
        "street": l.street,
        "zip": l.zip,
        "city": l.city,
        "district": l.district,
        "lat": l.lat,
        "lng": l.lng,
        "position_approx": l.position_approx,
        "available_from": l.available_from,
        "image_url": l.image_url,
        "wbs_required": l.wbs_required,
        "commission": l.commission,
        "score": l.score,
        "score_reasons": l.score_reasons,
    }


async def run(ziel: Path, criteria: Criteria) -> Dict[str, Any]:
    gefunden, status = await collect(criteria)
    listings = merge(gefunden, ziel)

    daten = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "city": criteria.city,
        "sources": status,
        "count": len(listings),
        "listings": listings,
    }
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text(json.dumps(daten, ensure_ascii=False, indent=1))
    return daten


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Angebote sammeln und als JSON ablegen.")
    parser.add_argument("-o", "--out", default="site/data/listings.json", type=Path)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    daten = asyncio.run(run(args.out, Criteria()))

    print(f"{daten['count']} Angebote -> {args.out}")
    for quelle, stand in sorted(daten["sources"].items()):
        print(f"  {quelle:9} {stand}")
    # Keine einzige Quelle geliefert? Dann ist etwas grundsaetzlich kaputt,
    # und die Action soll rot werden statt still eine leere Liste zu committen.
    if not any(s.endswith("Angebote") for s in daten["sources"].values()):
        print("FEHLER: keine einzige Quelle hat geliefert", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
