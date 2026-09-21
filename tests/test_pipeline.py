"""End-to-End ohne Netz: Angebot -> Nachricht -> Ja -> Text -> Versand.

Dieser Test ist die Absicherung der Nahtstelle zwischen beiden Tracks.
Wenn er bricht, habt ihr euch gegenseitig etwas kaputtgemacht.
"""

import json
import pathlib

import pytest

from flatfinder.adapters.base import Adapter, Blocked
from flatfinder.adapters.vonovia import VonoviaAdapter, _is_flat
from flatfinder.apply.compose import Bewerbung
from flatfinder.config import Criteria, Profile, Settings
from flatfinder.db import Store
from flatfinder.messenger.base import Answer, Messenger
from flatfinder.models import ApplicationStatus, Decision, ListingStatus
from flatfinder.pipeline import Pipeline

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "vonovia_list_ffm.json"


class FakeAdapter(Adapter):
    source = "vonovia"

    def __init__(self, listings=None, raise_blocked=False):
        self._listings = listings or []
        self._raise = raise_blocked

    async def fetch(self):
        if self._raise:
            raise Blocked("gesperrt")
        return list(self._listings)


class FakeMessenger(Messenger):
    name = "fake"

    def __init__(self):
        self.asked: list[tuple] = []
        self.notes: list[str] = []

    async def ask(self, listing, application_id, reasons):
        self.asked.append((listing.key, application_id))
        return f"msg-{application_id}"

    async def notify(self, text):
        self.notes.append(text)


class FakeComposer:
    def compose(self, listing):
        return Bewerbung(subject=f"Bewerbung {listing.title[:30]}",
                         body="Sehr geehrte Damen und Herren, " + "x " * 60,
                         hook="Stadtteil")


@pytest.fixture
def listings():
    raw = json.loads(FIXTURE.read_text())["results"]
    return [VonoviaAdapter.parse(i) for i in raw if _is_flat(i)]


def build(tmp_path, listings, notify_only=False, **crit):
    """notify_only=False fuer die Bewerbungs-Tests: die pruefen den Pfad,
    der im Alarm-Modus bewusst abgeschaltet ist."""
    store = Store(tmp_path / "t.db")
    msg = FakeMessenger()
    crit.setdefault("notify_threshold", 50)
    criteria = Criteria(price_max=1400, price_ideal=1000, sqm_min=50,
                        rooms_min=1, rooms_max=5, **crit)
    p = Pipeline(store, msg, Settings(dry_run=True, notify_only=notify_only),
                 criteria, Profile(), adapters=[FakeAdapter(listings)])
    p._composer = FakeComposer()
    return p, store, msg


async def test_voller_durchlauf_bis_versand(tmp_path, listings):
    p, store, msg = build(tmp_path, listings[:1])

    assert await p.collect() == 1
    assert len(msg.asked) == 1, "Angebot haette gemeldet werden muessen"

    listing_key, app_id = msg.asked[0]
    assert store.get(listing_key).status is ListingStatus.NOTIFIED

    await p.decide(Answer(application_id=app_id, yes=True, raw="yes"))

    app = store.get_application(app_id)
    assert app.status is ApplicationStatus.SENT
    assert app.decision is Decision.YES
    assert app.sent_via == "dry_run"          # DRY_RUN: nichts wirklich raus
    assert "Bewerbung" in app.message_text
    assert store.get(listing_key).status is ListingStatus.HANDLED


async def test_nein_sendet_nichts(tmp_path, listings):
    p, store, msg = build(tmp_path, listings[:1])
    await p.collect()
    _, app_id = msg.asked[0]

    await p.decide(Answer(app_id, yes=False, raw="no"))

    app = store.get_application(app_id)
    assert app.status is ApplicationStatus.REJECTED
    assert app.message_text is None, "Bei Nein darf kein Text generiert werden"
    assert app.sent_at is None


async def test_zweiter_lauf_meldet_nicht_erneut(tmp_path, listings):
    """Der teuerste Bug waere, denselben Vermieter zweimal anzuschreiben."""
    p, store, msg = build(tmp_path, listings[:3])
    await p.collect()
    erste_runde = len(msg.asked)
    assert erste_runde > 0

    await p.collect()   # Adapter liefert exakt dieselben Objekte nochmal
    assert len(msg.asked) == erste_runde, "Doppelte Meldung!"


async def test_doppelklick_auf_ja_sendet_einmal(tmp_path, listings):
    p, store, msg = build(tmp_path, listings[:1])
    await p.collect()
    _, app_id = msg.asked[0]

    await p.decide(Answer(app_id, True, "yes"))
    gesendet_um = store.get_application(app_id).sent_at
    await p.decide(Answer(app_id, True, "yes"))   # nochmal getippt

    assert store.get_application(app_id).sent_at == gesendet_um


async def test_gesperrter_adapter_wird_abgeschaltet_nicht_umgangen(tmp_path):
    store = Store(tmp_path / "t.db")
    msg = FakeMessenger()
    adapter = FakeAdapter(raise_blocked=True)
    p = Pipeline(store, msg, Settings(dry_run=True, notify_only=True),
                 Criteria(), Profile(), adapters=[adapter])

    await p.collect()

    assert adapter.enabled is False, "Gesperrter Adapter muss aus sein"
    assert any("gesperrt" in n for n in msg.notes), "David muss es erfahren"


async def test_auto_ja_ist_standardmaessig_aus(tmp_path, listings):
    p, store, msg = build(tmp_path, listings[:1], auto_yes_after_minutes=0)
    await p.collect()
    _, app_id = msg.asked[0]

    await p.sweep()

    app = store.get_application(app_id)
    assert app.status is ApplicationStatus.EXPIRED
    assert app.sent_at is None, "Ohne Freigabe darf nie etwas rausgehen"


async def test_auto_ja_greift_nur_ueber_der_schwelle(tmp_path, listings):
    p, store, msg = build(tmp_path, listings, auto_yes_after_minutes=0,
                          auto_yes_enabled=True, auto_yes_threshold=85)
    await p.collect()
    await p.sweep()

    apps = store.applications()
    gesendet = [a for a in apps if a.status is ApplicationStatus.SENT]
    abgelaufen = [a for a in apps if a.status is ApplicationStatus.EXPIRED]

    for a in gesendet:
        assert (store.get(a.listing_key).score or 0) >= 85
        assert a.decision is Decision.AUTO_YES
    for a in abgelaufen:
        assert (store.get(a.listing_key).score or 0) < 85


# ---------------- Alarm-Modus (der Standard) ----------------

async def test_alarmmodus_meldet_ohne_zu_bewerben(tmp_path, listings):
    """NOTIFY_ONLY=true ist der Standard: finden und melden, sonst nichts.
    Kein Anschreiben, keine Textgenerierung, keine Kosten."""
    p, store, msg = build(tmp_path, listings[:3], notify_only=True)

    await p.collect()

    assert msg.notes, "Es haette gemeldet werden muessen"
    assert not msg.asked, "Im Alarm-Modus darf nicht nach Ja/Nein gefragt werden"
    assert store.applications() == [], "Im Alarm-Modus entsteht keine Bewerbung"
    gemeldet = [l for l in store.recent(50) if l.status is ListingStatus.NOTIFIED]
    assert gemeldet


async def test_alarmmodus_meldet_kein_objekt_zweimal(tmp_path, listings):
    p, store, msg = build(tmp_path, listings[:3], notify_only=True)
    await p.collect()
    erste = len(msg.notes)
    await p.collect()
    assert len(msg.notes) == erste, "Dasselbe Objekt wurde erneut gemeldet"


async def test_alarmmodus_meldet_nur_ueber_der_schwelle(tmp_path, listings):
    p, store, msg = build(tmp_path, listings, notify_only=True,
                          notify_threshold=85)
    await p.collect()

    gemeldet = [l for l in store.recent(50) if l.status is ListingStatus.NOTIFIED]
    verworfen = [l for l in store.recent(50) if l.status is ListingStatus.DISCARDED]
    assert all((l.score or 0) >= 85 for l in gemeldet)
    assert all((l.score or 0) < 85 for l in verworfen)
    assert len(msg.notes) == len(gemeldet)


# ---------------- Aussetzer einer Quelle ----------------

def test_aussetzer_markiert_angebote_nicht_als_verschwunden(tmp_path):
    """Am 2026-09-21 lieferte Vonovia einmal nichts. Die 15 vorhandenen
    Wohnungen standen danach als "weg" in der Liste, obwohl sie noch da
    waren. Eine Quelle, die nicht geantwortet hat, darf ueber ihre
    Angebote nichts aussagen."""
    import json
    from datetime import datetime, timezone

    from flatfinder.export import merge

    datei = tmp_path / "listings.json"
    datei.write_text(json.dumps({"listings": [
        {"key": "vonovia:1", "source": "vonovia", "title": "Wohnung A",
         "first_seen": "2026-09-20T10:00:00+00:00",
         "last_seen": datetime.now(timezone.utc).isoformat(), "gone": False},
        {"key": "nhw:9", "source": "nhw", "title": "Wohnung B",
         "first_seen": "2026-09-20T10:00:00+00:00",
         "last_seen": datetime.now(timezone.utc).isoformat(), "gone": False},
    ]}))

    # nhw hat geantwortet (und dieses Objekt nicht mehr gemeldet),
    # vonovia gar nicht.
    raus = {e["key"]: e for e in merge([], datei, erfolgreich={"nhw"})}

    assert raus["vonovia:1"]["gone"] is False, "Aussetzer darf nicht als weg gelten"
    assert raus["nhw:9"]["gone"] is True, "Echt verschwunden muss weiterhin auffallen"


def test_ohne_angabe_gilt_alles_als_erfolgreich(tmp_path):
    """Rueckwaertskompatibel: ohne die Erfolgsliste verhaelt sich merge wie
    vorher."""
    import json
    from datetime import datetime, timezone

    from flatfinder.export import merge

    datei = tmp_path / "listings.json"
    datei.write_text(json.dumps({"listings": [
        {"key": "vonovia:1", "source": "vonovia", "first_seen": "2026-09-20T10:00:00+00:00",
         "last_seen": datetime.now(timezone.utc).isoformat(), "gone": False},
    ]}))
    raus = {e["key"]: e for e in merge([], datei)}
    assert raus["vonovia:1"]["gone"] is True
