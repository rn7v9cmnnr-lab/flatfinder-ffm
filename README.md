# flatfinder-ffm

Durchsucht stündlich die Frankfurter Wohnungsportale und zeigt die Treffer
in einer Weboberfläche — **ohne dass ein Rechner von dir läuft.**

```
GitHub Action (stündlich)  →  docs/data/listings.json  →  GitHub Pages
     sucht alle Quellen          committet ins Repo        Oberfläche
```

Kein Server, keine Hosting-Kosten, von überall erreichbar. Filtern,
sortieren und Details ansehen passiert im Browser — Filteränderungen wirken
sofort, ohne neuen Suchlauf.

**Status: läuft.** Drei Quellen, zuletzt 42 Angebote. 55 Tests, alle ohne
Netz, grün auf Python 3.9 und 3.13.

<details>
<summary>Automatische Bewerbungen (gebaut, aber abgeschaltet)</summary>

Im Repo liegt eine vollständige Bewerbungs-Strecke: Ja/Nein-Buttons im
Messenger, Textgenerierung mit Claude Opus 5, Versand per Formular-POST oder
SMTP, Bewerbungs-Tracking. Einschalten mit `NOTIFY_ONLY=false`.

Nicht gelöscht, weil getesteter Code, der wieder gebraucht werden kann.
Nicht im Weg, weil vom Pfad genommen. Die Textgenerierung wurde nie gegen
die echte API getestet — dafür fehlte der `ANTHROPIC_API_KEY`.
</details>

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

Im Alarm-Modus ist **Breite das ganze Produkt**: je mehr Quellen, desto besser.
Deshalb teilt ihr euch nach Quellen auf, nicht nach Schichten.

| | **Einer von euch** | **Der andere** |
|---|---|---|
| Verzeichnisse | `adapters/` (neue Quellen) | `scoring.py`, `docs/index.html` |
| Typische Aufgabe | „wg-gesucht-Adapter bauen" | „Scoring nachschärfen", „Kartenansicht" |

Adapter sind vollständig voneinander unabhängig — zwei Leute können an zwei
Quellen arbeiten, ohne sich je in dieselbe Datei zu setzen.

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
| **NHW** ✅ | server-gerendertes HTML, kein Bot-Schutz | VPS |
| **GWH** ✅ | TYPO3/Solr-JSON auf `cms.gwh.de`, Kaltmiete aus dem Detail | VPS |
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

## Python-Versionen

Das Projekt läuft ab **3.9**, damit es auf einem frischen Mac ohne
Vorbereitung startet. Getestet wird gegen 3.9 und 3.13.

Zwei Stellen kosten das:

- `compat.py` bringt `StrEnum` für alles unter 3.11 mit — inklusive
  `__str__`, sonst landet `"ListingStatus.NEW"` statt `"new"` in der
  Datenbank.
- Typen in Pydantic-Modellen stehen als `Optional[X]` und `List[X]`, nicht
  als `X | None` und `list[X]`. Pydantic wertet sie zur Laufzeit aus, und
  vor 3.10 gibt es `|` für Typen nicht.

Die Bewerbungstexte mit Claude brauchen als Einzige 3.10+ (das
anthropic-SDK). Deshalb ist das Paket optional (`pip install -e ".[apply]"`)
und wird erst beim tatsächlichen Gebrauch importiert. Der Alarm-Modus läuft
ohne.

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

### Rezept für eine neue Quelle, die nicht server-gerendert ist

So wurde der GWH-Endpunkt gefunden — dauert zwei Minuten:

1. Suchseite im Browser öffnen, F12 → **Netzwerk** → Filter **Fetch/XHR**
2. Seite neu laden und filtern
3. Den Request suchen, dessen Antwort die Wohnungen enthält
4. Rechtsklick → *Copy as cURL* → nachbauen

Bei GWH war das `cms.gwh.de/rentalentities.json`. Wichtig: die Suchseite war
`/mietangebote`, nicht `/immobiliensuche` — letztere ist nur eine Landingpage.

### Weitere Quellen

- [ ] **ABG Frankfurt Holding** — von außen TLS-Fehler, lokal gegenprüfen
- [ ] **wg-gesucht** — HTML ist offen, nur melden (Kontaktstrecke ist in
      robots.txt gesperrt, im Alarm-Modus egal)
- [ ] **IS24 / Kleinanzeigen / Immowelt** — sperren Rechenzentrums-IPs.
      Statt selbst zu bauen: [flathunter](https://github.com/flathunters/flathunter)
      auf dem Heim-Node laufen lassen und seinen Notifier auf `/ingest`
      zeigen. Spart die Adapter-Pflege für vier Portale.
