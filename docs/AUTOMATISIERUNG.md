# Benachrichtigungen und Bewerbungen

## Jetzt verfügbar

Zwei verbundene Tabs: Wohnungssuche und Benachrichtigungen & Bewerbung. Bis zu zehn Suchaufträge speichern vollständige Filter und den aufgelösten Umkreismittelpunkt. Vorschau und Wohnungssuche nutzen dieselbe Filterlogik in search.js. Die Aufträge sind Momentaufnahmen: Filteränderungen in der Suche ändern sie nicht stillschweigend.

Empfängeradresse, persönliche Vorstellung und bearbeitbare Bewerbungsvorlage bleiben im localStorage des Browsers. Kein Login, keine geräteübergreifende Synchronisation, kein aktiver Versand. Der JSON-Export enthält ausschließlich Suchaufträge, ohne Bewerberprofil, Empfängeradresse oder Zugangsdaten. Diese erste Ausbaustufe entspricht dem Wunsch, zunächst die Schablone zu bauen.

## Geplanter E-Mail-Ablauf

1. Eigene Gmail-Adresse als Absender einrichten; persönliche Adresse als Empfänger verwenden. Für SMTP sind smtp.gmail.com und TLS vorgesehen. Ein App-Passwort erfordert ein dafür geeignetes Google-Konto mit Zwei-Faktor-Anmeldung; andernfalls OAuth vorsehen. [Google-Anleitung](https://support.google.com/accounts/answer/185833?hl=de).
2. Absender, App-Passwort und Empfänger ausschließlich in GitHub-Secrets hinterlegen. Keine Passwörter in der Website, JSON unter docs/, Browser-Speicher oder Repository-Dateien.
3. Einen Notification-Worker nach erfolgreichem Suchlauf ergänzen. Exportierte Suchaufträge privat konfigurieren; den gemeinsamen Filtercode aus search.js auch dort verwenden. Nur neu gefundene, aktuell passende Wohnungen melden.
4. Dauerhafte Zustellungshistorie pro Empfänger, Suchauftrag und Angebots-ID vorsehen. Erst nach erfolgreicher SMTP-Annahme als gemeldet markieren; unklare Zustellungen gesondert behandeln. Ein neuer Auftrag braucht eine explizite Regel für vorhandene Treffer, damit nicht sofort hunderte Mails entstehen.
5. Erst Testmail an die eigene Adresse, danach aktivieren. Status der Einrichtung muss authentifiziert zurück in die Oberfläche gelangen; eine lokale Checkbox ist kein Nachweis einer aktiven Automation.

Mit GitHub Actions erfolgt die Benachrichtigung erst nach dem nächsten tatsächlich gestarteten Suchlauf; der Zeitplan ist keine Echtzeitgarantie.

## Später: Ja → Bewerbung

Ein bloßes Ja per E-Mail ist ohne Bezug auf Wohnung und Entwurf mehrdeutig. Benötigt werden eindeutige Angebots-/Entwurfs-ID, authentifizierte Freigabe, festgeschriebener Text und bestätigter Empfänger. Nicht direkt durch einen GET-Link versenden: Mailprogramme können Links vorab aufrufen. Stattdessen eine Vorschauseite öffnen und dort per POST bestätigen. Freigaben einmalig, zeitlich begrenzt und gegen Wiederholung geschützt speichern.

GitHub Pages allein kann keine privaten Profile speichern, eingehenden Antworten verarbeiten oder SMTP-Geheimnisse schützen. Für mobile Freigaben und gemeinsame Nutzung ist ein kleiner authentifizierter Dienst mit persistenter Datenbank sinnvoll. Die vorhandene FastAPI-/Pipeline-/Messenger-Strecke im src-Verzeichnis ist ein Ausgangspunkt, aber nicht an die statische Website angeschlossen. Vor Aktivierung sind insbesondere Identitätsprüfung der Messenger-Absender, CSRF-/Replay-Schutz, atomare Versandzustände und der tatsächliche Kontaktweg jedes Portals zu prüfen.

Bewerbungen werden je Plattform erst nach Prüfung ihres Kontaktwegs angebunden. Ohne geeigneten Kontaktweg bleibt Kopieren und Öffnen des Originalangebots. Keine erfundenen Profilangaben. Telegram/WhatsApp sind im neuen Tab als spätere Erweiterung gekennzeichnet.
