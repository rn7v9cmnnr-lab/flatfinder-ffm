"""Die Pipeline. Hier treffen sich Track A und Track B.

    collect()   Adapter -> Dedupe -> Score -> ggf. Nachricht    [Track A]
    decide()    Ja/Nein vom Messenger -> Text -> Versand        [Track B]
    sweep()     Timeouts abraeumen, Auto-Ja                     [beide]
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from .adapters.base import Adapter, Blocked
from .apply.compose import Composer
from .apply.senders import SendError, send
from .config import Criteria, Profile, Settings
from .db import Store
from .messenger.base import Answer, Messenger, summary
from .models import ApplicationStatus, Decision, ListingStatus
from .scoring import score as score_listing

log = logging.getLogger(__name__)


class Pipeline:
    def __init__(self, store: Store, messenger: Messenger, settings: Settings,
                 criteria: Criteria, profile: Profile,
                 adapters: list[Adapter] | None = None) -> None:
        self.store = store
        self.messenger = messenger
        self.settings = settings
        self.criteria = criteria
        self.profile = profile
        self.adapters = adapters or []
        self._composer: Composer | None = None

    @property
    def composer(self) -> Composer:
        if self._composer is None:
            self._composer = Composer(self.settings, self.profile)
        return self._composer

    # ---------------- Track A ----------------

    async def collect(self) -> int:
        """Alle Adapter durchlaufen. Ein kaputter Adapter darf die anderen
        nicht mitreissen - Wohnungssuche laeuft weiter."""
        neu = 0
        for adapter in self.adapters:
            if not adapter.enabled:
                continue
            try:
                listings = await adapter.fetch()
            except Blocked as e:
                # Gesperrt: abschalten, nicht umgehen. Siehe DECISIONS.md.
                log.error("%s gesperrt, Adapter deaktiviert: %s", adapter.source, e)
                adapter.enabled = False
                await self.messenger.notify(
                    f"⚠️ Adapter *{adapter.source}* wurde gesperrt und ist aus. "
                    f"Andere Quellen laufen weiter.")
                continue
            except Exception as e:
                log.exception("%s fehlgeschlagen: %s", adapter.source, e)
                continue

            for listing in listings:
                if self.store.is_known(listing):
                    continue
                pkt, gruende = score_listing(listing, self.criteria)
                listing.score, listing.score_reasons = pkt, gruende
                listing.status = (ListingStatus.SCORED if pkt >= self.criteria.notify_threshold
                                  else ListingStatus.DISCARDED)
                self.store.upsert(listing)
                neu += 1
                if listing.status is ListingStatus.SCORED:
                    await self._ask(listing)
        return neu

    async def _ask(self, listing) -> None:
        if self.settings.notify_only:
            # Alarm-Modus: melden und fertig. Keine Bewerbung, keine Buttons,
            # keine Kosten fuer Textgenerierung.
            await self.messenger.notify(summary(listing, listing.score_reasons))
            listing.status = ListingStatus.NOTIFIED
            self.store.upsert(listing)
            return

        app = self.store.create_application(listing.key)
        if app is None:
            log.info("%s: Bewerbung existiert schon, keine zweite Nachricht", listing.key)
            return
        try:
            ref = await self.messenger.ask(listing, app.id, listing.score_reasons)
        except Exception as e:
            log.exception("Nachricht fuer %s fehlgeschlagen: %s", listing.key, e)
            return
        app.messenger_ref = ref
        self.store.update_application(app)
        listing.status = ListingStatus.NOTIFIED
        self.store.upsert(listing)

    # ---------------- Track B ----------------

    async def decide(self, answer: Answer) -> None:
        app = self.store.get_application(answer.application_id)
        if app is None:
            log.warning("Antwort auf unbekannte Bewerbung %s", answer.application_id)
            return
        if app.status is not ApplicationStatus.PENDING:
            # Doppelklick auf den Button, oder Antwort nach Auto-Ja.
            log.info("Bewerbung %s ist schon %s - ignoriert", app.id, app.status)
            return

        app.decision = Decision.YES if answer.yes else Decision.NO
        app.decided_at = datetime.now(timezone.utc)

        if not answer.yes:
            app.status = ApplicationStatus.REJECTED
            self.store.update_application(app)
            return

        app.status = ApplicationStatus.APPROVED
        self.store.update_application(app)
        await self._compose_and_send(app)

    async def _compose_and_send(self, app) -> None:
        listing = self.store.get(app.listing_key)
        if listing is None:
            app.status, app.error = ApplicationStatus.FAILED, "Listing verschwunden"
            self.store.update_application(app)
            return

        app.status = ApplicationStatus.COMPOSING
        self.store.update_application(app)
        try:
            text = self.composer.compose(listing)
        except Exception as e:
            log.exception("Textgenerierung fehlgeschlagen fuer %s", listing.key)
            app.status, app.error = ApplicationStatus.FAILED, f"Text: {e}"
            self.store.update_application(app)
            await self.messenger.notify(f"❌ Text fuer {listing.title[:40]} fehlgeschlagen: {e}")
            return

        app.message_text = f"{text.subject}\n\n{text.body}"
        app.message_model = self.settings.anthropic_model
        app.status = ApplicationStatus.SENDING
        self.store.update_application(app)

        try:
            via = await send(listing, text, self.settings, self.profile)
        except (SendError, Exception) as e:
            log.exception("Versand fehlgeschlagen fuer %s", listing.key)
            app.status, app.error = ApplicationStatus.FAILED, f"Versand: {e}"
            self.store.update_application(app)
            await self.messenger.notify(f"❌ Versand an {listing.title[:40]} fehlgeschlagen: {e}")
            return

        app.sent_via, app.sent_at = via, datetime.now(timezone.utc)
        app.status = ApplicationStatus.SENT
        self.store.update_application(app)
        listing.status = ListingStatus.HANDLED
        self.store.upsert(listing)

        hinweis = " (DRY_RUN - nichts wirklich raus)" if self.settings.dry_run else ""
        await self.messenger.notify(
            f"✅ Bewerbung raus{hinweis}: {listing.title[:50]}\n\n_{text.body[:300]}…_")

    # ---------------- Timeouts ----------------

    async def sweep(self) -> None:
        """Unbeantwortete Nachrichten abraeumen.

        Nachts um drei schlaefst du. Ein Top-Treffer, der auf deine Antwort
        wartet, ist morgens weg. Deshalb Auto-Ja ab einem Score, dem du
        vertraust - standardmaessig AUS.
        """
        grenze = datetime.now(timezone.utc) - timedelta(
            minutes=self.criteria.auto_yes_after_minutes)
        for app in self.store.pending_applications():
            if app.created_at > grenze:
                continue
            listing = self.store.get(app.listing_key)
            if listing is None:
                continue
            darf_auto = (self.criteria.auto_yes_enabled
                         and (listing.score or 0) >= self.criteria.auto_yes_threshold)
            if darf_auto:
                log.info("Auto-Ja fuer %s (Score %s)", listing.key, listing.score)
                app.decision = Decision.AUTO_YES
                app.decided_at = datetime.now(timezone.utc)
                app.status = ApplicationStatus.APPROVED
                self.store.update_application(app)
                await self._compose_and_send(app)
            else:
                app.status = ApplicationStatus.EXPIRED
                self.store.update_application(app)
