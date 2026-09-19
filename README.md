# flatfinder-ffm

Wohnungssuche Frankfurt: findet Angebote, bewertet sie, meldet sie aufs Handy
und verschickt auf ein „Ja" eine individuell geschriebene Bewerbung.

```
Adapter → Dedupe → Scoring → Nachricht [Ja]/[Nein] → Claude schreibt → Versand
```

**Status:** Vonovia-Adapter läuft gegen echte Daten. Pipeline, Scoring,
Speicher, Messenger und Weboberfläche stehen. Textgenerierung ist gebaut,
aber noch nicht gegen die echte API getestet (API-Key fehlt).

---

## In 5 Minuten lauffähig

```bash
git clone <repo> && cd flatfinder-ffm
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env      # Profil und Kriterien ausfüllen
pytest -q                 # 11 Tests, laufen ohne Netz
uvicorn flatfinder.web.app:app --reload
```

Dashboard: http://localhost:8000

`DRY_RUN=true` ist Standard: Texte werden generiert, **nichts wird
verschickt**. Erst umstellen, wenn ihr zehn generierte Texte gelesen habt.

### Telegram anbinden (5 Minuten, kostenlos)

1. In Telegram **@BotFather** anschreiben → `/newbot` → Namen vergeben
2. Token nach `TELEGRAM_BOT_TOKEN` in `.env`
3. Dem eigenen Bot einmal `/start` schreiben
4. `https://api.telegram.org/bot<TOKEN>/getUpdates` aufrufen → `chat.id`
   nach `TELEGRAM_CHAT_ID`

---

## Arbeitsteilung

Zwei Tracks, die sich **nur an zwei DB-Tabellen** berühren. Deshalb könnt ihr
parallel arbeiten, ohne euch zu blockieren.

| | **Track A — Finden & Melden** | **Track B — Texten & Senden** |
|---|---|---|
| Verzeichnisse | `adapters/`, `scoring.py`, `db.py` (Listings) | `apply/`, `messenger/`, `web/` |
| Schreibt | Tabelle `listings` | Tabelle `applications` |
| Typische Aufgabe | „NHW-Adapter bauen" | „Bewerbungstext verbessern" |

**Gemeinsam und zuerst:** `models.py`. Das ist der Vertrag. Änderungen daran
gehen immer in einen eigenen PR mit Review vom jeweils anderen — sonst
brecht ihr euch gegenseitig den Code, ohne es zu merken.

### Regeln, die das Projekt am Leben halten

1. **`main` ist geschützt.** Alles über Branch + PR, auch Einzeiler.
2. **Ein Adapter = ein PR = ein Fixture-Test.** Keine Ausnahme. Ein Adapter
   ohne Fixture ist eine Zeitbombe, die beim nächsten Portal-Update hochgeht.
3. **Tests dürfen nie ins Netz.** `pytest` muss im Zug ohne Empfang laufen.
4. **Entscheidungen nach `DECISIONS.md`**, eine Zeile. Verhindert
   Endlosdiskussionen in Woche drei.
5. **Nie zwei Leute in derselben Datei.** Die Track-Aufteilung oben sorgt
   dafür, dass das fast nie vorkommt.

### Neue Quelle bauen

```python
from .base import HttpAdapter
from ..models import Listing

class MeineQuelle(HttpAdapter):
    source = "meinequelle"

    async def fetch(self) -> list[Listing]:
        r = await self.get("https://…")
        return [self.parse(x) for x in r.json()["results"]]

    @staticmethod
    def parse(item: dict) -> Listing:   # statisch = ohne Netz testbar
        return Listing(source="meinequelle", source_id=…, url=…, title=…)
```

Dazu `tests/fixtures/meinequelle_*.json` (echte Antwort einfrieren) und
`tests/test_meinequelle.py`. Fertig.

---

## Quellenlage (gemessen am 2026-09-19)

| Quelle | Zugang | Wo es läuft |
|---|---|---|
| **Vonovia** ✅ | offene JSON-API, `X-VON-Search-Token`, Paging über `offset` | VPS |
| **NHW** | server-gerendertes HTML, kein Bot-Schutz | VPS |
| **GWH** | server-gerendertes HTML (Nuxt SSR) | VPS |
| wg-gesucht | HTML offen — Kontaktstrecke aber in robots.txt gesperrt | VPS, nur melden |
| Kleinanzeigen | sperrt Rechenzentrums-IPs pauschal | **Heim-Node** |
| ImmoScout24 | 401 vom Rechenzentrum, starke Bot-Erkennung | **Heim-Node**, eingeloggt |
| Immowelt/Immonet | 403; Kontaktstrecke in robots.txt gesperrt | offen |

### Warum zwei Rechner

```
   VPS (~4 €/Monat)                Heim-Node (Raspi / alter Laptop)
   ├─ Core, Web, Scoring           ├─ IS24         (Playwright, eingeloggt)
   ├─ Vonovia, NHW, GWH            └─ Kleinanzeigen
   ├─ Claude-Textgenerierung             │
   └─ Versand  ◄──────── POST /ingest ───┘
```

Kleinanzeigen und IS24 blocken Rechenzentrums-IPs pauschal — gemessen, nicht
vermutet. Der Heim-Node baut die Verbindung nach außen auf, also kein
Port-Forwarding im Router nötig.

---

## Grenzen, die wir bewusst ziehen

- **Kein Captcha-Löser, keine Proxy-Rotation.** Wir automatisieren einen
  eingeloggten Account im menschlichen Tempo. Sperrt uns eine Quelle, wird
  der Adapter abgeschaltet, nicht getarnt (`Blocked` → `enabled=False`, per
  Test abgesichert).
- **Keine Vollautomatik bei wg-gesucht und Immowelt.** Dort steht die
  Kontaktstrecke ausdrücklich in der `robots.txt`. Dort nur melden.
- **Keine erfundenen Angaben.** Der Prompt verbietet dem Modell ausdrücklich,
  Einkommen, Beruf oder Referenzen zu erfinden. Fehlt etwas im Profil, wird
  es weggelassen.
- **Eine Bewerbung pro Objekt**, per UNIQUE-Index in der DB erzwungen.

Ausführlich in [DECISIONS.md](DECISIONS.md).

---

## Was noch fehlt

- [ ] NHW- und GWH-Adapter (HTML-Parsing, Gerüst steht)
- [ ] Bewerbermappe als PDF automatisch anhängen ← **größter Hebel**
- [ ] IS24-Adapter (Playwright, Heim-Node)
- [ ] Entscheidung: auf [flathunter](https://github.com/flathunters/flathunter)
      aufsetzen statt vier Adapter selbst zu pflegen?
- [ ] Rückmeldungen der Vermieter erfassen (`REPLIED`)
