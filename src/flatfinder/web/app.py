"""Lokaler Betrieb der Weboberflaeche.

Zeigt dieselbe Seite wie die gehostete Fassung (docs/index.html) und
schreibt nach jedem Durchlauf dieselbe Datendatei. Dadurch gibt es nur
EINE Oberflaeche zu pflegen - was hier funktioniert, funktioniert auch
auf GitHub Pages, und umgekehrt.

Gehostet braucht man diesen Dienst gar nicht: dort sucht eine GitHub
Action und Pages liefert docs/ aus. Lokal ist er praktisch, wenn man
sofort suchen will oder an den Adaptern arbeitet.

Ausserdem hier: die Webhooks fuer Telegram/WhatsApp und der
Ingest-Endpunkt fuer einen Heim-Node (fuer Quellen, die
Rechenzentrums-IPs sperren).
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import (FileResponse, HTMLResponse, PlainTextResponse,
                               RedirectResponse)
from fastapi.templating import Jinja2Templates

from ..adapters.gwh import GwhAdapter
from ..adapters.immowelt import ImmoweltAdapter
from ..adapters.nhw import NhwAdapter
from ..adapters.wggesucht import WgGesuchtAdapter
from ..export import merge as export_merge
from ..adapters.vonovia import VonoviaAdapter
from ..config import Criteria, Profile, Settings
from ..db import Store
from ..messenger.telegram import TelegramMessenger
from ..messenger.whatsapp import WhatsAppMessenger, build as build_messenger
from ..models import Listing
from ..pipeline import Pipeline

log = logging.getLogger(__name__)
TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

#: Die gehostete Oberflaeche. Liegt in docs/, weil GitHub Pages nur "/" oder
#: "/docs" ausliefern kann.
SITE = Path(__file__).resolve().parents[3] / "docs"
DATEN = SITE / "data" / "listings.json"

settings = Settings()
criteria = Criteria()
profile = Profile()
store = Store(settings.db_path)
messenger = build_messenger(settings)

pipeline = Pipeline(store, messenger, settings, criteria, profile,
                    adapters=[
                        VonoviaAdapter(criteria.city),
                        NhwAdapter(criteria.city),
                        GwhAdapter(criteria.city),
                        WgGesuchtAdapter(criteria.city),
                        ImmoweltAdapter(criteria.city),
                    ])


@asynccontextmanager
async def lifespan(app: FastAPI):
    sched = AsyncIOScheduler()
    sched.add_job(_tick, "interval", seconds=settings.poll_interval_seconds,
                  max_instances=1, coalesce=True)
    sched.add_job(pipeline.sweep, "interval", minutes=1, max_instances=1)
    sched.start()
    log.info("Scheduler laeuft, Intervall %ss, Quellen: %s",
             settings.poll_interval_seconds,
             ", ".join(a.source for a in pipeline.adapters))
    # Erster Durchlauf sofort, damit das Dashboard nicht leer startet.
    asyncio.create_task(_tick())
    yield
    sched.shutdown(wait=False)
    for adapter in pipeline.adapters:
        if hasattr(adapter, "aclose"):
            await adapter.aclose()


#: Zustand des letzten Durchlaufs, fuer die Anzeige im Dashboard.
LAUF: dict[str, object] = {"zeit": None, "neu": 0, "fehler": None, "laeuft": False}
_lock = asyncio.Lock()


async def _tick() -> None:
    """Ein Durchlauf ueber alle Quellen. Laeuft stuendlich und auf Knopfdruck.

    Das Lock verhindert, dass ein Klick auf "Jetzt suchen" parallel zum
    Zeitplan laeuft - sonst holen beide dieselben Objekte und melden doppelt.
    """
    if _lock.locked():
        log.info("Durchlauf laeuft bereits, uebersprungen")
        return
    async with _lock:
        LAUF["laeuft"] = True
        try:
            LAUF["neu"] = await pipeline.collect()
            LAUF["fehler"] = None
            _schreibe_daten()
            log.info("Durchlauf fertig: %s neue Objekte", LAUF["neu"])
        except Exception as e:
            LAUF["fehler"] = str(e)
            log.exception("Durchlauf fehlgeschlagen")
        finally:
            LAUF["zeit"] = datetime.now(timezone.utc)
            LAUF["laeuft"] = False


def _schreibe_daten() -> None:
    """Denselben Datenstand erzeugen, den auch die GitHub Action schreibt."""
    import json

    listings = store.recent(limit=2000)
    eintraege = export_merge(listings, DATEN)
    DATEN.parent.mkdir(parents=True, exist_ok=True)
    DATEN.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "city": criteria.city,
        "sources": {a.source: ("aus" if not a.enabled else "aktiv")
                    for a in pipeline.adapters},
        "count": len(eintraege),
        "listings": eintraege,
    }, ensure_ascii=False, indent=1))


app = FastAPI(title="flatfinder-ffm", lifespan=lifespan)


# ---------------- Dashboard ----------------

@app.get("/", response_class=HTMLResponse)
async def startseite():
    """Dieselbe Seite wie auf GitHub Pages."""
    return HTMLResponse((SITE / "index.html").read_text(encoding="utf-8"))


@app.get("/data/listings.json")
async def daten():
    """Die Datendatei. Wird nach jedem Durchlauf neu geschrieben."""
    if not DATEN.exists():
        _schreibe_daten()
    return FileResponse(DATEN, media_type="application/json",
                        headers={"Cache-Control": "no-store"})


@app.get("/alt", response_class=HTMLResponse)
async def dashboard_alt(request: Request, alle: int = 0):
    """alle=1 zeigt auch die aussortierten Objekte - zum Nachjustieren
    der Kriterien, wenn zu wenig durchkommt."""
    listings = store.recent(limit=300)
    if not alle:
        listings = [l for l in listings if (l.score or 0) >= criteria.notify_threshold]
    listings.sort(key=lambda l: (-(l.score or 0), l.price_per_sqm or 999))

    apps = store.applications(limit=200)
    frisch = datetime.now(timezone.utc) - timedelta(hours=24)

    return TEMPLATES.TemplateResponse(request, "dashboard.html", {
        "listings": listings,
        "apps": {a.listing_key: a for a in apps},
        "settings": settings,
        "criteria": criteria,
        "lauf": LAUF,
        "alle": bool(alle),
        "frisch_ab": frisch,
        "quellen": [a.source for a in pipeline.adapters if a.enabled],
        "quellen_aus": [a.source for a in pipeline.adapters if not a.enabled],
        "stats": {
            "treffer": len(listings),
            "gesamt": len(store.recent(limit=1000)),
            "quellen": sum(1 for a in pipeline.adapters if a.enabled),
        },
    })


@app.post("/suchen")
async def suchen_jetzt():
    """Durchlauf sofort ausloesen, statt auf die naechste Stunde zu warten."""
    asyncio.create_task(_tick())
    return RedirectResponse("/", status_code=303)


@app.get("/bewerbung/{app_id}", response_class=HTMLResponse)
async def application_detail(request: Request, app_id: int):
    app_obj = store.get_application(app_id)
    if app_obj is None:
        raise HTTPException(404)
    return TEMPLATES.TemplateResponse(request, "application.html", {
        "app": app_obj, "listing": store.get(app_obj.listing_key)})


@app.get("/health", response_class=PlainTextResponse)
async def health():
    return "ok"


# ---------------- Webhooks ----------------

@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    payload = await request.json()
    answer = TelegramMessenger.parse_answer(payload)
    if answer:
        await pipeline.decide(answer)
    return {"ok": True}


@app.get("/webhook/whatsapp", response_class=PlainTextResponse)
async def whatsapp_verify(request: Request):
    """Meta verifiziert den Webhook einmalig mit einem Challenge-Token."""
    q = request.query_params
    if (q.get("hub.mode") == "subscribe"
            and q.get("hub.verify_token") == settings.whatsapp_verify_token):
        return q.get("hub.challenge", "")
    raise HTTPException(403, "verify_token stimmt nicht")


@app.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request):
    payload = await request.json()
    answer = WhatsAppMessenger.parse_answer(payload)
    if answer:
        await pipeline.decide(answer)
    return {"ok": True}


# ---------------- Heim-Node ----------------

def _check_ingest_token(x_ingest_token: str = Header(default="")) -> None:
    if not settings.ingest_token or x_ingest_token != settings.ingest_token:
        raise HTTPException(401, "ungueltiger Ingest-Token")


@app.post("/ingest", dependencies=[Depends(_check_ingest_token)])
async def ingest(listings: list[Listing]):
    """Der Heim-Node schickt hierher, was er von IS24 und Kleinanzeigen
    geholt hat. Dieselbe Verarbeitung wie bei den lokalen Adaptern."""
    from ..models import ListingStatus
    from ..scoring import score as score_listing

    neu = 0
    for listing in listings:
        if store.is_known(listing):
            continue
        pkt, gruende = score_listing(listing, criteria)
        listing.score, listing.score_reasons = pkt, gruende
        listing.status = (ListingStatus.SCORED if pkt >= criteria.notify_threshold
                          else ListingStatus.DISCARDED)
        store.upsert(listing)
        neu += 1
        if listing.status is ListingStatus.SCORED:
            await pipeline._ask(listing)
    return {"angenommen": len(listings), "neu": neu}
