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


def test_structured_rental_end_is_preserved_as_fixed_term(html):
    listings = {l.source_id: l for l in WgGesuchtAdapter.parse_page(html, "Frankfurt am Main")}
    temporary = listings["14106813"]
    assert temporary.available_from == "01.10.2026"
    assert "Befristete Mietzeit: 01.10.2026 bis 31.03.2027." in temporary.description
    assert "Befristete Mietzeit" not in listings["14108331"].description
    assert listings["14108331"].available_from == "01.10.2026"
    assert "bis 31.12.2036" in listings["7905205"].description


def test_full_title_is_kept_for_exclusion_detection(html):
    from selectolax.parser import HTMLParser
    tree = HTMLParser(html)
    node = tree.css_first("div.offer_list_item")
    title = node.css_first("h2.truncate_title a")
    full = "Schöne Wohnung. " + "Mit viel Licht und Platz. " * 6 + "Nur Zwischenmiete."
    title.replace_with(HTMLParser("<a href='/wohnungen-in-Frankfurt.123.html'>" + full + "</a>").css_first("a"))
    listing = WgGesuchtAdapter.parse_item(node, "Frankfurt am Main")
    assert len(listing.title) <= 110
    assert "Zwischenmiete" not in listing.title
    assert "Zwischenmiete" in listing.description
