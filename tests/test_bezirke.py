"""Stadtteil-Mittelpunkte - die Grundlage des Umkreisfilters."""

import pytest

from flatfinder.bezirke import MITTELPUNKTE, finde


def test_tabelle_ist_gefuellt():
    assert len(MITTELPUNKTE) >= 30


def test_alle_punkte_liegen_im_rhein_main_gebiet():
    """Ein Tippfehler in den Koordinaten wuerde den Umkreisfilter still
    verfaelschen - deshalb eine grobe Plausibilitaetsgrenze."""
    for name, (lat, lng) in MITTELPUNKTE.items():
        assert 49.9 < lat < 50.3, f"{name}: Breitengrad {lat} ausserhalb"
        assert 8.4 < lng < 8.9, f"{name}: Laengengrad {lng} ausserhalb"


@pytest.mark.parametrize("eingabe", [
    "Bockenheim", "bockenheim", " Bockenheim ", "Frankfurt-Bockenheim",
])
def test_schreibweisen(eingabe):
    pos = finde(eingabe)
    assert pos is not None, eingabe
    assert abs(pos[0] - 50.123) < 0.02


@pytest.mark.parametrize("tippfehler,erwartet", [
    ("Norweststadt", "Nordweststadt"),
    ("Preugnisheim", "Preungesheim"),
    ("Sachsenhausen Oberrad", "Sachsenhausen"),
])
def test_tippfehler_der_portale_werden_aufgeloest(tippfehler, erwartet):
    assert finde(tippfehler) == MITTELPUNKTE[erwartet]


@pytest.mark.parametrize("name", ["Westend-Süd", "Nordend-Ost", "Innenstadt I"])
def test_genauer_teilstadtteil_schlaegt_den_uebergeordneten(name):
    """Ein Alias darf einen exakt bekannten Stadtteil nicht ueberschreiben -
    der eigene Mittelpunkt liegt naeher als der des Oberbezirks."""
    assert finde(name) == MITTELPUNKTE[name]


def test_unbekanntes_gibt_none():
    assert finde("Quatschhausen") is None
    assert finde("") is None
    assert finde(None) is None
