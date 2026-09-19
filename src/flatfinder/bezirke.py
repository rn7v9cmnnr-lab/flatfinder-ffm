"""Mittelpunkte der Frankfurter Stadtteile.

Wofuer: Die Portale (wg-gesucht, Immowelt) liefern keine Koordinaten, nur
einen Stadtteil. Ohne Naeherung wuerde der Umkreisfilter zwei Drittel der
Angebote nicht erfassen.

Die Werte stammen einmalig von OpenStreetMap/Nominatim und liegen seitdem
fest im Projekt - im Betrieb wird also kein fremder Dienst gefragt, es gibt
keine Ratenbegrenzung und Tests brauchen kein Netz.

Genauigkeit: Stadtteilmitte, typisch einige hundert Meter daneben. Fuer
"liegt das noch in meiner Ecke" reicht das; fuer "wie weit ist es genau"
nicht. Angebote, deren Position so geschaetzt wurde, sind mit
`position_approx = True` gekennzeichnet und in der Oberflaeche als
ungefaehr ausgewiesen.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

#: Stadtteil -> (lat, lng)
MITTELPUNKTE = {
    "Altstadt": (50.11044, 8.68235),
    "Bahnhofsviertel": (50.10841, 8.66815),
    "Bockenheim": (50.12331, 8.64606),
    "Bornheim": (50.12973, 8.71061),
    "Eckenheim": (50.15171, 8.67975),
    "Fechenheim": (50.12302, 8.76939),
    "Gallus": (50.10384, 8.6431),
    "Ginnheim": (50.14308, 8.64986),
    "Griesheim": (50.09143, 8.60786),
    "Hausen": (50.13201, 8.62436),
    "Innenstadt": (50.11456, 8.68359),
    "Innenstadt I": (50.11456, 8.68359),
    "Innenstadt IV": (50.11456, 8.68359),
    "Mitte-Nord": (50.15484, 8.66188),
    "Mitte-West": (50.13793, 8.61239),
    "Nied": (50.10073, 8.57221),
    "Niederrad": (50.08829, 8.64271),
    "Niederursel": (50.16906, 8.61888),
    "Nordend-Ost": (50.12492, 8.69232),
    "Nordend-West": (50.12491, 8.67795),
    "Nordweststadt": (50.1638, 8.6191),
    "Oberrad": (50.09973, 8.72291),
    "Ostend": (50.11237, 8.69997),
    "Preungesheim": (50.15654, 8.68782),
    "Riedberg": (50.17662, 8.63208),
    "Rödelheim": (50.12498, 8.61255),
    "Sachsenhausen": (50.10026, 8.6836),
    "Schwanheim": (50.0853, 8.58363),
    "Seckbach": (50.14343, 8.72589),
    "Sindlingen": (50.07984, 8.51767),
    "Süd": (50.06191, 8.63755),
    "West": (50.09803, 8.54634),
    "Nordend": (50.12811, 8.68713),
    "Westend": (50.11872, 8.66052),
    "Westend-Nord": (50.12636, 8.66792),
    "Westend-Süd": (50.11524, 8.66227),
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

    Vertraegt Schreibweisen der Portale: Gross-/Kleinschreibung,
    "Frankfurt-Bockenheim", "Bockenheim (Frankfurt)", und die bekannten
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
