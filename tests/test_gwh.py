"""GWH-Adapter gegen eingefrorene echte Antworten.

Fixture vom 2026-09-19: 12 Frankfurter Objekte + 13 andere Staedte.
"""

import json
import pathlib

import pytest

from flatfinder.adapters.gwh import GwhAdapter, _de_euro, _de_float, _dig_base_rent

FIX = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture
def docs():
    return json.loads((FIX / "gwh_rentalentities.json").read_text())["documents"]["list"]["results"]


def test_parst_pflichtfelder(docs):
    for d in docs:
        l = GwhAdapter.parse(d)
        assert l is not None
        assert l.source == "gwh"
        assert l.source_id and "/" not in l.source_id and " " not in l.source_id
        assert l.url.startswith("https://www.gwh.de/mietangebote/detail/")
        assert l.sqm and l.sqm > 0
        assert l.rooms and l.rooms >= 1
        assert l.commission is False


def test_overalrent_ist_warmmiete_nicht_kaltmiete(docs):
    """Der API-Feldname 'overalRent' (ein l) ist die GESAMTmiete. Wer den als
    Kaltmiete verbucht, filtert jede bezahlbare Wohnung weg."""
    l = GwhAdapter.parse(docs[0])
    assert l.price_warm is not None
    assert l.price_cold is None, "Kaltmiete steht nicht in der Listen-Antwort"


def test_kaltmiete_aus_der_detailantwort():
    detail = json.loads((FIX / "gwh_detail_priceset.json").read_text())
    assert _dig_base_rent(detail) == 736


def test_kaltmiete_aus_kaputter_antwort_bricht_nicht():
    for muell in ({}, {"content": []}, {"content": [{}]}, {"content": [{"content": {}}]}):
        assert _dig_base_rent(muell) is None


def test_stadtfilter(docs):
    alle = [GwhAdapter.parse(d) for d in docs]
    ffm = [l for l in alle if "frankfurt" in (l.city or "").lower()]
    assert len(ffm) == 12


def test_adresse_wird_zusammengesetzt(docs):
    """street + houseNumber kommen getrennt und muessen zusammen."""
    l = GwhAdapter.parse(docs[0])
    assert l.street and any(ch.isdigit() for ch in l.street)


@pytest.mark.parametrize("roh,erwartet", [
    ("1.016,00", 1016), ("736,00", 736), ("890", 890),
    ("0,00", None), ("", None), (None, None), ("abc", None),
])
def test_deutsches_euroformat(roh, erwartet):
    assert _de_euro(roh) == erwartet


@pytest.mark.parametrize("roh,erwartet", [
    ("72,5", 72.5), ("100", 100.0), ("1.234,5", 1234.5), (None, None), ("0", None),
])
def test_deutsches_zahlenformat(roh, erwartet):
    assert _de_float(roh) == erwartet


def test_ersatztitel_wenn_die_api_nur_eine_objektnummer_liefert():
    """Einige GWH-Objekte haben keinen Titel; dann steht dort die
    Objektnummer ('1600/13513/16'), was in der Liste unlesbar ist."""
    from flatfinder.adapters.gwh import _title

    assert _title({"title": "1600/13513/16", "numberOfRooms": "2",
                   "overallSpace": "64,4", "street": "Ben-Gurion-Ring",
                   "houseNumber": 50}) == "2-Zimmer-Wohnung, 64 m2, Ben-Gurion-Ring 50"
    assert _title({"title": "", "numberOfRooms": "3", "city": "Frankfurt am Main"}) \
        == "3-Zimmer-Wohnung, Frankfurt am Main"
    # Echte Titel bleiben unangetastet
    assert _title({"title": "Schöne 2-Zimmer-Wohnung mit Balkon"}) \
        == "Schöne 2-Zimmer-Wohnung mit Balkon"


def test_kein_objekt_behaelt_eine_objektnummer_als_titel(docs):
    for d in docs:
        l = GwhAdapter.parse(d)
        assert not all(ch.isdigit() or ch in "/-. " for ch in l.title), \
            f"Objektnummer als Titel durchgerutscht: {l.title!r}"
