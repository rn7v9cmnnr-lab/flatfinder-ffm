"""Bewertet ein Listing von 0-100. Bestimmt, ob und wie dringend gemeldet wird.

Absichtlich simpel und nachvollziehbar: jede Regel gibt Punkte und einen
Grund. Die Gruende landen in der Nachricht, damit du siehst, WARUM der Bot
etwas vorschlaegt - und das Scoring nachjustieren kannst, statt ihm zu glauben.
"""

from __future__ import annotations

from .config import Criteria
from .models import Listing

# Harte Ausschlusskriterien -> Score 0, keine Nachricht.
KO_GRUENDE = "ko"


def score(listing: Listing, c: Criteria) -> tuple[int, list[str]]:
    reasons: list[str] = []

    # --- K.o.-Kriterien ---
    if listing.price_cold and listing.price_cold > c.price_max:
        return 0, [f"Kaltmiete {listing.price_cold} EUR ueber Limit {c.price_max} EUR"]
    if listing.sqm and listing.sqm < c.sqm_min:
        return 0, [f"{listing.sqm:.0f} m2 unter Minimum {c.sqm_min:.0f} m2"]
    if listing.rooms and not (c.rooms_min <= listing.rooms <= c.rooms_max):
        return 0, [f"{listing.rooms:.0f} Zimmer ausserhalb {c.rooms_min:.0f}-{c.rooms_max:.0f}"]
    if listing.wbs_required and not c.accept_wbs:
        return 0, ["WBS erforderlich"]
    if listing.commission and not c.accept_commission:
        return 0, ["Provisionspflichtig"]
    if listing.district and listing.district in c.districts_excluded:
        return 0, [f"Stadtteil {listing.district} ausgeschlossen"]

    pts = 50
    reasons.append("Grundkriterien erfuellt")

    # --- Preis ---
    if listing.price_cold:
        if listing.price_cold <= c.price_ideal:
            pts += 20
            reasons.append(f"Kaltmiete {listing.price_cold} EUR im Wunschbereich")
        else:
            # linear abfallend zwischen ideal und max
            span = max(c.price_max - c.price_ideal, 1)
            over = listing.price_cold - c.price_ideal
            pts += int(20 * (1 - over / span))

    # --- Preis pro Quadratmeter (der ehrlichere Indikator) ---
    ppsm = listing.price_per_sqm
    if ppsm:
        if ppsm <= 13:
            pts += 15
            reasons.append(f"{ppsm:.2f} EUR/m2 - guenstig fuer Frankfurt")
        elif ppsm <= 16:
            pts += 8
        elif ppsm > 20:
            pts -= 10
            reasons.append(f"{ppsm:.2f} EUR/m2 - teuer")

    # --- Lage ---
    if listing.district and c.districts_preferred:
        if listing.district in c.districts_preferred:
            pts += 12
            reasons.append(f"Wunschlage {listing.district}")

    # --- Groesse ---
    if listing.sqm and listing.sqm >= c.sqm_min + 15:
        pts += 5
        reasons.append(f"{listing.sqm:.0f} m2 - grosszuegig")

    # --- Keine Provision ist bares Geld ---
    if listing.commission is False:
        pts += 5
        reasons.append("provisionsfrei")

    return max(0, min(100, pts)), reasons
