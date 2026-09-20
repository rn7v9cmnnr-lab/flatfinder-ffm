"""Positionen fuer den Umkreisfilter: Stadtteile und Postleitzahlen.

Wofuer: Die Portale (wg-gesucht, Immowelt) liefern keine Koordinaten.
Manche lassen sogar den Stadtteil weg und nennen nur eine PLZ. Ohne
Naeherung waere der Umkreisfilter fuer einen grossen Teil der Angebote
wirkungslos.

Reihenfolge beim Nachschlagen: exakte Koordinaten der Quelle > Stadtteil >
Postleitzahl. Die PLZ ist der verlaesslichste Rueckfall - sie steht fast
immer da und ist eindeutig, waehrend Stadtteilnamen fehlen oder falsch
geschrieben sein koennen ("Norweststadt", "Preugnisheim").

Die Werte stammen einmalig von OpenStreetMap/Nominatim und liegen seitdem
fest im Projekt: im Betrieb wird kein fremder Dienst gefragt, es gibt keine
Ratenbegrenzung, und Tests brauchen kein Netz.

Genauigkeit: Mittelpunkt des Stadtteils bzw. des PLZ-Gebiets, typisch
einige hundert Meter daneben. Fuer "liegt das noch in meiner Ecke" reicht
das. Angebote, deren Position so geschaetzt wurde, tragen
`position_approx = True` und sind in der Oberflaeche mit ~ ausgewiesen.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

#: Stadtteil -> (lat, lng)
MITTELPUNKTE = {
    "Altstadt": (50.11044, 8.68235),
    "Bahnhofsviertel": (50.10841, 8.66815),
    "Bergen-Enkheim": (50.15807, 8.76189),
    "Berkersheim": (50.17329, 8.69731),
    "Bockenheim": (50.12331, 8.64606),
    "Bonames": (50.18135, 8.66333),
    "Bornheim": (50.12973, 8.71061),
    "Dornbusch": (50.13905, 8.67527),
    "Eckenheim": (50.15171, 8.67975),
    "Eschersheim": (50.1582, 8.65621),
    "Fechenheim": (50.12302, 8.76939),
    "Frankfurter Berg": (50.16802, 8.67569),
    "Gallus": (50.10384, 8.6431),
    "Ginnheim": (50.14308, 8.64986),
    "Griesheim": (50.09143, 8.60786),
    "Harheim": (50.18229, 8.69297),
    "Hausen": (50.13201, 8.62436),
    "Höchst": (50.09947, 8.54526),
    "Innenstadt": (50.11456, 8.68359),
    "Innenstadt I": (50.11456, 8.68359),
    "Innenstadt IV": (50.11456, 8.68359),
    "Kalbach": (50.18148, 8.65585),
    "Mitte-Nord": (50.15484, 8.66188),
    "Mitte-West": (50.13793, 8.61239),
    "Nied": (50.10073, 8.57221),
    "Nieder-Erlenbach": (50.20261, 8.71196),
    "Nieder-Eschbach": (50.20177, 8.66658),
    "Niederrad": (50.08829, 8.64271),
    "Niederursel": (50.16906, 8.61888),
    "Nordend": (50.12811, 8.68713),
    "Nordend-Ost": (50.12492, 8.69232),
    "Nordend-West": (50.12491, 8.67795),
    "Nordweststadt": (50.1638, 8.6191),
    "Oberrad": (50.09973, 8.72291),
    "Ostend": (50.11237, 8.69997),
    "Praunheim": (50.1508, 8.62151),
    "Preungesheim": (50.15654, 8.68782),
    "Rebstock": (50.10837, 8.60316),
    "Riedberg": (50.17662, 8.63208),
    "Riederwald": (50.12884, 8.73313),
    "Rödelheim": (50.12498, 8.61255),
    "Sachsenhausen": (50.10026, 8.6836),
    "Schwanheim": (50.0853, 8.58363),
    "Seckbach": (50.14343, 8.72589),
    "Sindlingen": (50.07984, 8.51767),
    "Sossenheim": (50.12012, 8.56662),
    "Süd": (50.06191, 8.63755),
    "Unterliederbach": (50.11041, 8.53225),
    "West": (50.09803, 8.54634),
    "Westend": (50.11872, 8.66052),
    "Westend-Nord": (50.12636, 8.66792),
    "Westend-Süd": (50.11524, 8.66227),
    "Zeilsheim": (50.09556, 8.49478),
}

#: Postleitzahl -> (lat, lng). Alle Frankfurter PLZ.
PLZ = {
    "60306": (50.11607, 8.67018),
    "60308": (50.11236, 8.6528),
    "60310": (50.11061, 8.67285),
    "60311": (50.11066, 8.68289),
    "60312": (50.1115, 8.67316),
    "60313": (50.11554, 8.68287),
    "60314": (50.11468, 8.72409),
    "60316": (50.11977, 8.69703),
    "60318": (50.1253, 8.68649),
    "60320": (50.1383, 8.67735),
    "60322": (50.12557, 8.67627),
    "60323": (50.12478, 8.66423),
    "60325": (50.11611, 8.65857),
    "60326": (50.10155, 8.62709),
    "60327": (50.10046, 8.64544),
    "60329": (50.10716, 8.66645),
    "60385": (50.12479, 8.71379),
    "60386": (50.12698, 8.7553),
    "60388": (50.15739, 8.76325),
    "60389": (50.14672, 8.7169),
    "60431": (50.14437, 8.65095),
    "60433": (50.1642, 8.66904),
    "60435": (50.15957, 8.69649),
    "60437": (50.19746, 8.68195),
    "60438": (50.17828, 8.62677),
    "60439": (50.16295, 8.62346),
    "60486": (50.11399, 8.62625),
    "60487": (50.12763, 8.64011),
    "60488": (50.14164, 8.61503),
    "60489": (50.1257, 8.605),
    "60528": (50.06912, 8.64069),
    "60529": (50.07958, 8.58013),
    "60549": (50.04272, 8.56734),
    "60594": (50.10489, 8.69633),
    "60596": (50.09718, 8.67062),
    "60598": (50.08093, 8.67935),
    "60599": (50.08491, 8.71535),
    "65929": (50.09989, 8.53398),
    "65931": (50.09008, 8.50227),
    "65933": (50.09738, 8.59765),
    "65934": (50.1039, 8.57569),
    "65936": (50.1205, 8.57433),
}

#: Schreibweisen und Tippfehler der Quellen auf echte Stadtteile abbilden.
ALIASE = {
    "innenstadt i": "Innenstadt",
    "innenstadt ii": "Innenstadt",
    "innenstadt iii": "Innenstadt",
    "mitte-nord": "Innenstadt",
    "nordend-ost": "Nordend",
    "nordend-west": "Nordend",
    "norweststadt": "Nordweststadt",
    "preugnisheim": "Preungesheim",
    "sachsenhausen oberrad": "Sachsenhausen",
    "sachsenhausen-nord": "Sachsenhausen",
    "sachsenhausen-süd": "Sachsenhausen",
    "westend-nord": "Westend",
    "westend-süd": "Westend",
}

#: Nachschlagen ohne Ruecksicht auf Gross-/Kleinschreibung.
_KLEIN = {k.lower(): v for k, v in MITTELPUNKTE.items()}


def _schlag_nach(name: str) -> Optional[Tuple[float, float]]:
    k = name.lower()
    if k in _KLEIN:
        return _KLEIN[k]
    ziel = ALIASE.get(k)
    if ziel:
        return _KLEIN.get(ziel.lower())
    return None


def finde(stadtteil: Optional[str]) -> Optional[Tuple[float, float]]:
    """Naeherungsposition fuer einen Stadtteilnamen, oder None.

    Vertraegt die Schreibweisen der Portale: Gross-/Kleinschreibung,
    "Frankfurt-Bockenheim", "Bockenheim (Frankfurt)" und die bekannten
    Tippfehler aus ALIASE.
    """
    if not stadtteil:
        return None
    name = re.sub(r"\s+", " ", stadtteil).strip()
    if not name:
        return None

    treffer = _schlag_nach(name)
    if treffer:
        return treffer

    kern = re.sub(r"(frankfurt|am main|\(|\))", "", name, flags=re.I).strip(" -,")
    if kern and kern.lower() != name.lower():
        return _schlag_nach(kern)
    return None


def finde_plz(plz: Optional[str]) -> Optional[Tuple[float, float]]:
    """Naeherungsposition ueber die Postleitzahl."""
    if not plz:
        return None
    m = re.search(r"\b(\d{5})\b", str(plz))
    return PLZ.get(m.group(1)) if m else None


def stadtteil_zu_plz(plz: Optional[str]) -> Optional[str]:
    """Naechstgelegener Stadtteil zu einer PLZ.

    Fuer Angebote, bei denen die Quelle keinen Stadtteil mitliefert - die
    Oberflaeche kann dann trotzdem nach Stadtteil filtern, statt dass das
    Angebot durch jeden Stadtteilfilter faellt.
    """
    pos = finde_plz(plz)
    if pos is None:
        return None
    return min(MITTELPUNKTE,
               key=lambda n: (MITTELPUNKTE[n][0] - pos[0]) ** 2
                           + (MITTELPUNKTE[n][1] - pos[1]) ** 2)
