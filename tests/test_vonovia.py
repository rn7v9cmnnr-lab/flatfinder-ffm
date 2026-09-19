"""Adapter-Tests laufen ohne Netz - gegen eingefrorene echte Antworten.

Wenn Vonovia sein Format aendert, bricht der Live-Lauf, nicht dieser Test.
Deshalb: Fixture nach jedem bestaetigten Format-Wechsel neu ziehen (siehe
scripts/refresh_fixtures.py).
"""

import json
import pathlib

import pytest

from flatfinder.adapters.vonovia import VonoviaAdapter, _is_flat

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "vonovia_list_ffm.json"


@pytest.fixture
def raw():
    return json.loads(FIXTURE.read_text())["results"]


def test_parst_wohnung_vollstaendig(raw):
    flats = [i for i in raw if _is_flat(i)]
    assert flats, "Fixture enthaelt keine Wohnung - neu ziehen?"
    l = VonoviaAdapter.parse(flats[0])

    assert l.source == "vonovia"
    assert l.source_id
    assert l.url.startswith("https://www.vonovia.de/immobilien/")
    assert l.price_cold and l.price_cold > 0
    assert l.sqm and l.sqm > 0
    assert l.rooms and l.rooms >= 1
    assert l.zip and len(l.zip) == 5
    assert l.commission is False
    # Ohne diese beiden Felder kann Track B sich nicht bewerben:
    assert l.contact_form_url
    assert l.contact_payload and l.contact_payload.get("wrkID") == l.source_id


def test_filtert_garagen_und_stellplaetze(raw):
    """Vonovia mischt Garagen in denselben Endpunkt - die duerfen nie melden."""
    for item in raw:
        if not _is_flat(item):
            continue
        titel = (item.get("titel") or "").lower()
        assert "garage" not in titel and "stellplatz" not in titel
        assert float(item["groesse"]) > 0
        assert float(item["anzahl_zimmer"]) >= 1


def test_trennt_stadtteil_vom_ort(raw):
    """'Frankfurt am Main OT Schwanheim' -> city + district getrennt."""
    parsed = [VonoviaAdapter.parse(i) for i in raw if _is_flat(i)]
    mit_ot = [l for l in parsed if l.district]
    if mit_ot:
        assert all("OT" not in (l.city or "") for l in mit_ot)


def test_fingerprint_erkennt_dasselbe_objekt_auf_anderer_quelle(raw):
    flats = [i for i in raw if _is_flat(i)]
    a = VonoviaAdapter.parse(flats[0])
    # Dieselbe Wohnung, andere Quelle, 8 EUR Preisunterschied
    b = a.model_copy(update={
        "source": "is24", "source_id": "xyz",
        "price_cold": (a.price_cold or 0) + 8,
    })
    assert a.fingerprint == b.fingerprint
    assert a.key != b.key


def test_filtert_gewerbeflaechen(raw):
    """Am 2026-09-19 rutschte eine 116 m2 'Einzelhandels-/Buero-/Praxisflaeche'
    mit anzahl_zimmer=1 als Wohnung durch. Nur der Preis hat sie am Ende
    aussortiert - der Filter muss das selbst koennen."""
    from flatfinder.adapters.vonovia import NICHT_WOHNUNG

    for item in raw:
        if not _is_flat(item):
            continue
        titel = (item.get("titel") or "").lower()
        treffer = [w for w in NICHT_WOHNUNG if w in titel]
        assert not treffer, f"Gewerbe/Garage durchgerutscht: {item.get('titel')!r} ({treffer})"


def test_gewerbe_beispiel_wird_geblockt():
    assert not _is_flat({
        "vermarktungsart_miete": "1", "groesse": "115.6", "anzahl_zimmer": "1",
        "titel": "Helle, große Einzelhandels/Büro-/Praxisfläche mit großer Schaufensterfront",
    })
    # Gegenprobe: eine echte Wohnung darf nicht mitgefiltert werden
    assert _is_flat({
        "vermarktungsart_miete": "1", "groesse": "73.3", "anzahl_zimmer": "3",
        "titel": "3-Zimmer-Maisonette-Wohnung",
    })


async def test_adapter_funktioniert_ohne_async_with():
    """Der Webdienst baut Adapter beim Start und betritt nie einen
    async-Kontext. Frueher scheiterte dort jeder Durchlauf mit
    'Client fehlt'. Der Client muss sich selbst anlegen."""
    from flatfinder.adapters.vonovia import VonoviaAdapter

    a = VonoviaAdapter()
    try:
        assert a.client is not None          # kein AdapterError mehr
        c1 = a.client
        assert a.client is c1, "Client darf nicht bei jedem Zugriff neu entstehen"
    finally:
        await a.aclose()


async def test_adapter_erholt_sich_nach_aclose():
    """Nach einem Neustart des Schedulers darf ein geschlossener Client den
    Adapter nicht dauerhaft lahmlegen."""
    from flatfinder.adapters.vonovia import VonoviaAdapter

    a = VonoviaAdapter()
    _ = a.client
    await a.aclose()
    try:
        assert a.client is not None and not a.client.is_closed
    finally:
        await a.aclose()
