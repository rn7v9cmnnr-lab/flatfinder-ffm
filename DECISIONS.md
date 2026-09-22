# Entscheidungen

Eine Zeile pro Entscheidung, neueste oben. Verhindert, dass wir in Woche
drei dieselbe Diskussion nochmal führen. Wer etwas hier Stehendes ändern
will: Eintrag ergänzen, nicht überschreiben.

| Datum | Entscheidung | Warum |
|---|---|---|
| 2026-09-19 | **Python 3.11+**, httpx + selectolax, Playwright nur wo nötig | bestes Scraping-Ökosystem, beide können es |
| 2026-09-19 | **SQLite ohne ORM**, zwei Tabellen, expliziter SQL | zu zweit gut zu reviewen; Postgres erst bei echtem Bedarf |
| 2026-09-19 | **`Listing` und `Application` sind der Vertrag** zwischen den Tracks | ohne feste Naht blockieren sich zwei Leute dauernd |
| 2026-09-19 | **Telegram zuerst, WhatsApp als Ziel** hinter `Messenger`-Interface | WhatsApp-Vorlagen brauchen Meta-Freigabe und kosten ~0,055 USD/Nachricht; Entwicklung darf nicht darauf warten |
| 2026-09-19 | **Großvermieter zuerst** (Vonovia, NHW, GWH), IS24 zuletzt | gemessen: Vonovia hat offene JSON-API, IS24 gibt 401 vom Rechenzentrum |
| 2026-09-19 | **Zweigeteilter Betrieb**: Core auf VPS, IS24/Kleinanzeigen auf Heim-Node | beide Portale sperren Rechenzentrums-IPs pauschal (401 / "IP-Bereich gesperrt") |
| 2026-09-19 | **Kein Captcha-Löser, keine Proxy-Rotation** | Grenze zwischen Automatisierung des eigenen Accounts und Umgehen einer Schutzmaßnahme; flathunter braucht dafür Capmonster — bewusst nicht übernommen |
| 2026-09-19 | **Gesperrter Adapter wird abgeschaltet, nicht getarnt** (`Blocked` → `enabled=False`) | siehe oben; per Test abgesichert |
| 2026-09-19 | **Keine Vollautomatik bei wg-gesucht und Immowelt** | dort ist die Kontaktstrecke ausdrücklich in robots.txt gesperrt (`/nachricht-senden.html`, `GetAnbieterKontaktanfrageForm`) |
| 2026-09-19 | **`DRY_RUN=true` als Standard**, Auto-Ja standardmäßig aus | ein falsch konfigurierter Bot, der 200 Vermieter anschreibt, ist nicht zurückholbar |
| 2026-09-19 | **Eine Bewerbung pro Objekt**, per UNIQUE-Index erzwungen | doppeltes Anschreiben ist der teuerste denkbare Bug |
| 2026-09-19 | **Claude Opus 5** für die Textgenerierung, System-Prompt gecacht | ~2 ct pro Bewerbung; Textqualität ist das Alleinstellungsmerkmal gegenüber flathunter |
| 2026-09-19 | **Adapter-Tests laufen gegen Fixtures, nie gegen das Netz** | sonst ist die Suite rot, sobald ein Portal hustet |
| 2026-09-19 | **Zuschnitt auf Alarm-Tool** (`NOTIFY_ONLY=true`), stündlich | Davids Entscheidung; Breite schlägt Automatik |
| 2026-09-19 | **Bewerbungs-Strecke bleibt im Repo, abgeschaltet** statt gelöscht | getesteter Code, jederzeit per Flag zurück |
| 2026-09-19 | **Nach Quellen aufteilen, nicht nach Schichten** | im Alarm-Modus ist Breite das Produkt; Adapter sind voneinander unabhängig |
| 2026-09-19 | **Weboberfläche statt Handy-Nachricht** (`MESSENGER=web`) | Davids Entscheidung; spart Token, Meta-Konto und laufende Kosten |
| 2026-09-19 | **GWH: Kaltmiete per Detail-Request nachladen** | `overalRent` der Liste ist die WARMmiete; Scoring auf Warmmiete filtert jede bezahlbare Wohnung weg |
| 2026-09-19 | **HTTP-Client legt sich selbst an** statt `async with` zu erzwingen | der Webdienst baut Adapter beim Start und betritt nie einen async-Kontext |
| 2026-09-19 | **Python 3.9 statt 3.11 als Mindestversion** | macOS liefert 3.9; ohne das braucht man erst Homebrew, nur um eine Wohnungsliste zu sehen. Getestet gegen 3.9 und 3.13 |
| 2026-09-19 | **anthropic-SDK ist optional** und wird spät importiert | es braucht 3.10+; der Alarm-Modus soll nicht daran hängen |
| 2026-09-19 | **GitHub Actions + Pages statt VPS** | kostenlos, kein Server zu pflegen, von überall erreichbar; der Preis ist ein öffentliches Repo |
| 2026-09-19 | **Ordner heißt `docs/`, nicht `site/`** | GitHub Pages kann nur `/` oder `/docs` ausliefern |
| 2026-09-19 | **Die JSON-Datei ist das Gedächtnis**, keine Datenbank | jeder Action-Lauf startet in einem frischen Container; daraus kommt `first_seen` für die „neu"-Markierung |
| 2026-09-19 | **Breit sammeln, im Browser filtern** | Filteränderungen wirken sofort; zu eng gesammelt sieht man Angebote nie, ohne es zu merken |
| 2026-09-19 | **Eine Oberfläche für lokal und online** (`docs/index.html`) | zwei UIs zu pflegen wäre der sichere Weg, dass eine davon verrottet |
| 2026-09-19 | **Commit-Mails auf GitHub-Noreply umgeschrieben** | vor dem Öffentlichmachen; Davids private Adresse stand in jedem Commit |

| 2026-09-22 | **Karte folgt PLZ, Ort und Radius** | Neue Mittelpunkte öffnen die Karte mit zunächst 3 km; Preis-/Textfilter erhalten den Kartenausschnitt. Suchläufe bei Push nur auf main. |

## Offen

- [ ] Auf [flathunter](https://github.com/flathunters/flathunter) aufsetzen statt eigene Adapter für IS24/Kleinanzeigen/Immowelt/wg-gesucht? Spart die Adapter-Pflege, die dieses Projekt sonst tötet. Entscheidung fällt, bevor der erste dieser vier Adapter gebaut wird.
- [ ] ABG Frankfurt Holding: von außen TLS-Fehler, lokal gegenprüfen.

