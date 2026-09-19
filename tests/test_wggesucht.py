"""wg-gesucht-Adapter gegen eingefrorenes echtes HTML."""

import pathlib

import pytest

from flatfinder.adapters.wggesucht import WgGesuchtAdapter
from flatfinder.models import Kind

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "wggesucht_ffm.html"


@pytest.fixture
def html():
    return FIXTURE.read_text(encoding="utf-8", errors="replace")


def test_findet_alle_angebote(html):
    assert len(WgGesuchtAdapter.parse_page(html, "Frankfurt am Main")) == 28


def test_pflichtfelder(html):
    for l in WgGesuchtAdapter.parse_page(html, "Frankfurt am Main"):
        assert l.source == "wggesucht"
        assert l.kind is Kind.PORTAL
        assert l.source_id.isdigit()
        assert l.url.startswith("https://www.wg-gesucht.de/")
        assert l.title and len(l.title) <= 110


def test_preis_ist_warmmiete_nicht_kaltmiete(html):
    """wg-gesucht zeigt die Gesamtmiete. Wer die als Kaltmiete verbucht,
    haelt jede Wohnung faelschlich fuer zu teuer."""
    ls = WgGesuchtAdapter.parse_page(html, "Frankfurt am Main")
    mit_preis = [l for l in ls if l.price_warm is not None]
    assert mit_preis
    assert all(l.price_cold is None for l in ls)


def test_titel_wird_gekappt(html):
    """wg-gesucht packt die halbe Anzeige in den Titel - in einer Liste
    unlesbar. Am ersten Satzende kappen."""
    ls = WgGesuchtAdapter.parse_page(html, "Frankfurt am Main")
    assert all(len(l.title) <= 110 for l in ls)
    assert any(len(l.title) < 80 for l in ls)


def test_stadtteil_ohne_stadtnamen(html):
    for l in WgGesuchtAdapter.parse_page(html, "Frankfurt am Main"):
        if l.district:
            assert "frankfurt" not in l.district.lower()


def test_keine_kontaktstrecke(html):
    """robots.txt von wg-gesucht sperrt /nachricht-senden.html. Der Adapter
    darf gar keinen Kontaktweg anbieten."""
    for l in WgGesuchtAdapter.parse_page(html, "Frankfurt am Main"):
        assert l.contact_form_url is None
        assert l.contact_email is None
