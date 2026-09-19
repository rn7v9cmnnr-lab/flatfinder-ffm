"""Weboberflaeche + Webhooks.

Drei Aufgaben:
  1. Dashboard - was wurde gefunden, was wurde beworben, was kam zurueck
  2. Webhook-Endpunkte fuer Telegram und WhatsApp (die Ja/Nein-Antworten)
  3. Ingest-Endpunkt fuer den Heim-Node (IS24/Kleinanzeigen laufen dort,
     weil beide Rechenzentrums-IPs sperren)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates

from ..adapters.vonovia import VonoviaAdapter
from ..config import Criteria, Profile, Settings
from ..db import Store
from ..messenger.telegram import TelegramMessenger
from ..messenger.whatsapp import WhatsAppMessenger, build as build_messenger
from ..models import Listing
from ..pipeline import Pipeline

log = logging.getLogger(__name__)
TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

settings = Settings()
criteria = Criteria()
profile = Profile()
store = Store(settings.db_path)
messenger = build_messenger(settings)

pipeline = Pipeline(store, messenger, settings, criteria, profile,
                    adapters=[VonoviaAdapter(criteria.city)])


@asynccontextmanager
async def lifespan(app: FastAPI):
    sched = AsyncIOScheduler()
    sched.add_job(_tick, "interval", seconds=settings.poll_interval_seconds,
                  max_instances=1, coalesce=True)
    sched.add_job(pipeline.sweep, "interval", minutes=1, max_instances=1)
    sched.start()
    log.info("Scheduler laeuft, Intervall %ss, DRY_RUN=%s",
             settings.poll_interval_seconds, settings.dry_run)
    yield
    sched.shutdown(wait=False)


async def _tick() -> None:
    for adapter in pipeline.adapters:
        # Adapter, die eine private IP brauchen, laufen auf dem Heim-Node
        # und liefern ueber /ingest an. Hier waeren sie nur ein 401.
        if adapter.requires_residential_ip:
            continue
    try:
        neu = await pipeline.collect()
        if neu:
            log.info("%d neue Objekte", neu)
    except Exception:
        log.exception("Durchlauf fehlgeschlagen")


app = FastAPI(title="flatfinder-ffm", lifespan=lifespan)


# ---------------- Dashboard ----------------

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    listings = store.recent(limit=100)
    apps = store.applications(limit=100)
    by_key = {a.listing_key: a for a in apps}
    return TEMPLATES.TemplateResponse(request, "dashboard.html", {
        "listings": listings,
        "apps": by_key,
        "settings": settings,
        "criteria": criteria,
        "stats": {
            "gefunden": len(listings),
            "gemeldet": sum(1 for l in listings if l.score
                            and l.score >= criteria.notify_threshold),
            "beworben": sum(1 for a in apps if a.sent_at),
            "offen": sum(1 for a in apps if a.status == "pending"),
        },
    })


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
