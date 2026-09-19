"""NHW-Adapter gegen eingefrorenes echtes HTML.

Fixture vom 2026-09-19: 67 Angebote hessenweit, davon 15 in Frankfurt.
"""

import pathlib

import pytest

from flatfinder.adapters.nhw import NhwAdapter, _euro, _qm

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "nhw_wohnungsangebote.html"


@pytest.fixture
def html():
    return FIXTURE.read_text(encoding="utf-8", errors="replace")


def test_findet_alle_angebote(html):
    assert len(NhwAdapter.parse_page(html, "")) == 67


def test_stadtfilter_greift(html):
    ffm = NhwAdapter.parse_page(html, "Frankfurt am Main")
    assert len(ffm) == 15
    assert all("frankfurt" in (l.city or "").lower() for l in ffm)


def test_pflichtfelder_sind_gesetzt(html):
    for l in NhwAdapter.parse_page(html, "Frankfurt am Main"):
        assert l.source == "nhw"
        assert l.source_id and l.source_id != l.url, "Objektnummer aus URL erwartet"
        assert l.url.startswith("https://www.naheimst.de/")
        assert l.title and l.title != "Wohnung"
        assert l.sqm and l.sqm > 0
        assert l.rooms and l.rooms >= 1
        assert l.commission is False


def test_fehlender_preis_wird_none_nicht_null(html):
    """Fuenf moeblierte Apartments haben keine Nettokaltmiete. Die duerfen
    nicht als '0 EUR' durchgehen - sonst gewinnen sie jedes Scoring."""
    alle = NhwAdapter.parse_page(html, "")
    ohne_preis = [l for l in alle if l.price_cold is None]
    assert ohne_preis, "Fixture hat keine preislosen Angebote mehr - neu ziehen?"
    assert all(l.price_cold != 0 for l in alle)


def test_adresse_und_stadt_werden_getrennt(html):
    """'Offenbach am Main, Kettelerstraße 44' -> city + street"""
    alle = NhwAdapter.parse_page(html, "")
    mit_adresse = [l for l in alle if l.street]
    assert mit_adresse
    for l in mit_adresse:
        assert "," not in l.street, f"Stadt klebt noch in der Strasse: {l.street!r}"


def test_parst_labels_nicht_positionen(html):
    """Etage steht mal vor, mal hinter der Miete. Wenn wir nach Position
    parsen wuerden, landete 'EG' als Preis."""
    for l in NhwAdapter.parse_page(html, ""):
        if l.price_cold is not None:
            assert 100 < l.price_cold < 10000, f"unplausibler Preis: {l.price_cold}"


@pytest.mark.parametrize("roh,erwartet", [
    ("533,00 €", 533), ("1.549,00 €", 1549), ("1.234,56 €", 1234),
    ("", None), (None, None), ("EG", None),
])
def test_euro_parser(roh, erwartet):
    assert _euro(roh) == erwartet


@pytest.mark.parametrize("roh,erwartet", [
    ("53,17 m²", 53.17), ("92,80 m²", 92.8), ("104 m²", 104.0), (None, None),
])
def test_qm_parser(roh, erwartet):
    assert _qm(roh) == erwartet


def test_url_zeigt_auf_detailseite_nicht_aufs_formular(html):
    """selectolax wertet Komma-Selektoren von links nach rechts aus, nicht in
    Dokumentreihenfolge. Dadurch gewann frueher der 'Jetzt anfragen'-Link und
    jede URL endete auf #request."""
    for l in NhwAdapter.parse_page(html, ""):
        assert "#" not in l.url, f"Fragment in URL: {l.url}"
        assert "/immobilie/" in l.url
        assert l.contact_form_url.endswith("#request")
