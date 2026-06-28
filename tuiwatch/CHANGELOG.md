# Changelog

## [0.10.1] - 2026-06-28

### Fixed
- **Nächte-Vergleich: falsche Preise bei nicht buchbaren Dauern.** Bei Bereichs-Dauern
  wie `7-` lieferte TUI für nicht verfügbare Dauern (z. B. 8–10 Nächte) ersatzweise das
  nächstliegende Angebot (das 7-Nächte-Paket) zurück — diese Zeilen zeigten denselben
  Gesamtpreis und nur eine heruntergerechnete €/Nacht. Es wird nun geprüft, ob die
  **tatsächliche Reisedauer** der angefragten entspricht; weicht sie ab, erscheint
  korrekt „nicht abrufbar".

### Changed
- **Kleinere Buttons** in der Angebots-Fußzeile (kompaktere Schrift/Abstände), damit die
  Aktionsleiste weniger Platz braucht.

## [0.10.0] - 2026-06-28

### Added
- **Nächte-Vergleich**: neuer Button „Nächte" je Angebot öffnet einen Dialog, in dem
  sich per **− / +** eine Spanne einstellen lässt (Default 3, max ±7). Es werden live
  die Preise für **kürzere und längere Reisedauern** abgefragt (z. B. bei 10 Nächten:
  7–9 und 11–13) und als Tabelle gezeigt: **Preis p. P., € pro Nacht, Gesamt, Differenz**.
  Günstigste Zeile grün, aktuelle Dauer markiert; Dauern ohne Flug/Angebot erscheinen
  als „nicht abrufbar". Das Ergebnis wird gespeichert (mit „Neu abfragen").

## [0.9.1] - 2026-06-28

### Fixed
- **Preiskalender-Klick erzeugte ein ungültiges Datum** (HTTP 400 auf tui.com): Es wurde
  `startDate` = `endDate` = angeklickter Tag gesetzt, sodass der Reisezeitraum z. B.
  „21.05.2027 – 21.05.2027, 10 Nächte" lautete. Jetzt wird `endDate = Anreise + Nächte`
  berechnet (Hin- bis Rückreise), passend zur Reisedauer. Gilt für Links- und Rechtsklick
  (Termin öffnen / als neues Angebot speichern). Die Dauer kommt aus dem Preiskalender
  (`duration`).

## [0.9.0] - 2026-06-28

### Added
- **Archiv**: Angebote können archiviert werden — als Überblick über ältere/abgelaufene
  Reisen, ohne dass weiter live abgefragt wird.
  - **Automatisch**: sobald das Rückreisedatum in der Vergangenheit liegt, wandert ein
    Angebot ins Archiv (es ist ohnehin nicht mehr buchbar/abfragbar).
  - **Manuell**: Button „Archivieren" je Angebot (z. B. wenn ausgebucht / nicht mehr
    verfügbar) bzw. „Reaktivieren" zum Zurückholen.
  - Archivierte Angebote sind über den Schalter **„Archiv"** oben einblendbar (eigener
    Abschnitt, gedämpft dargestellt) und werden im Poller/„Alle prüfen", in der
    Übersicht (eigener Zähler + `archived_offers` am Summary-Sensor) und im E-Mail-Versand
    ausgenommen. Backup/Wiederherstellen nimmt den Archiv-Status mit.

### Fixed
- **Pauschalreise inkl. Transfer**: Offer-Abfrage nutzt jetzt `transferIncluded=true`
  (vorher `false`) — passend zur Buchung auf tui.com. Ein in der Original-URL gesetzter
  Wert hat weiterhin Vorrang.

## [0.8.1] - 2026-06-28

### Added
- **Preiskalender → Rechtsklick** auf einen Tag speichert genau diesen Termin als
  **neues, eigenständiges Angebot** (mit fixiertem Datum) und prüft ihn sofort. Linksklick
  öffnet den Termin weiterhin auf tui.com.

## [0.8.0] - 2026-06-28

### Added
- **E-Mail-Versand**: Button „Als E-Mail senden" verschickt alle Angebote als optisch
  aufbereitete HTML-Mail. Empfänger wird vor dem Senden eingegeben (Vorbelegung aus
  `smtp_to`/zuletzt genutzt). SMTP über neue Optionen `smtp_host/port/user/password/
  from/to/tls` (Muster wie MyPage). Footer mit Hinweis + GitHub-Link.
- **Backup & Wiederherstellen**: getrackte Angebote als JSON sichern und importieren
  (überspringt Duplikate, prüft neue sofort).
- **Übersicht** über der Liste: Anzahl Angebote, günstigstes Angebot, Anzahl unter
  Wunschpreis, pausierte — plus HA-**Summary-Sensor** `sensor.tuiwatch_uebersicht`
  (Wert = günstigster Preis; Attribute: günstigstes Angebot, Gesamtzahl, unter Wunschpreis).
- **Preiskalender-Heatmap**: Tage je nach Preis eingefärbt (grün→rot); **Klick auf einen
  Tag öffnet genau diesen Termin auf tui.com**.

## [0.7.2] - 2026-06-28

### Added
- **Ort öffnet Google Maps**: Klick auf den Ort (📍) öffnet das Hotel in Google Maps
  (Suchanfrage Hotelname + Ort; TUI liefert keine Koordinaten).

## [0.7.1] - 2026-06-28

### Changed
- **Konsole deutlich gesprächiger**: Prüfungen zeigen jetzt Name, Preis pro Person,
  Gesamtpreis, Verfügbarkeit und Quelle (API/Browser) sowie Preisänderungen. Zusätzlich
  protokolliert: Hinzufügen, Umbenennen, Pausieren/Fortsetzen, Wunschpreis, manuelle
  Prüfung, Vergleich-/Kalender-Start und gesendete Benachrichtigungen/Alarme.
- **Fehler werden rot markiert** (Log-Level ERROR), echte Ausfälle deutlich sichtbar;
  Ausweichen auf den Browser-Fallback erscheint gelb (WARNING). Verbose-Log zeigt die
  API-URLs zusätzlich.

## [0.7.0] - 2026-06-28

### Added
- **Tracking pausieren** je Angebot (ohne löschen): pausierte Angebote werden bei der
  automatischen Prüfung und „Alle prüfen" übersprungen; manuelles „Prüfen" bleibt
  möglich. Badge „⏸ pausiert" + abgedimmte Karte.
- **CSV-Export** der Preishistorie (Button im Verlauf-Fenster) — mit Excel-tauglichem
  Format (Semikolon, UTF-8-BOM).
- **PWA / installierbar**: Manifest, Service Worker und App-Icons (192/512) — TUIWatch
  lässt sich als App installieren (am besten über Direktzugriff/Reverse-Proxy).
- **Gesamtpreis** zusätzlich zum Preis pro Person (bei mehreren Reisenden) in der Karte
  und als HA-Sensor-Attribute `total_price` / `travellers`.

## [0.6.1] - 2026-06-28

### Fixed
- **Preiskalender bei Dauer-Bereichen** (z. B. `duration=7-` oder `9-12`) lieferte nichts.
  Der Kalender braucht eine einzelne Dauer — es wird jetzt die untere Zahl verwendet
  (wie auf der TUI-Seite).

### Changed
- **Ausführliches Logging** zeigt jetzt auch die **API-Abrufe (URLs) und Ergebnisse**
  in der Konsole (Offer-/Kalender-/Bewertungs-/Ort-Abruf), wenn `verbose_log` an ist.

## [0.6.0] - 2026-06-28

### Added
- **Günstigerer-Termin-Alarm**: Meldung (HA/Telegram), wenn der Preiskalender einen
  anderen Abreisetag deutlich günstiger zeigt als dein getrackter Preis (Schwelle per
  `cheaper_date_min_diff`, Standard 50 €). Aktualisiert nebenbei den Kalender-Cache.
- **Ausverkauft-/Fehler-Alarm**: Meldung, wenn ein Angebot mehrmals in Folge kein
  Ergebnis liefert (ausgebucht/URL veraltet), plus Entwarnung, sobald es wieder klappt.
  Optionen `notify_cheaper_date`, `cheaper_date_min_diff`, `notify_errors`.
- **Angebot umbenennen** direkt im UI (✎ neben dem Namen).
- **Sortierung** der Angebotsliste: Hinzugefügt, Preis, größte Preisänderung,
  Bewertung, Name.
- **Diagramm-Extras**: Wunschpreis-Linie, Vergleichspreis-Verlauf und grüne
  Marker für Preisrückgänge im Verlaufs-Diagramm.

## [0.5.1] - 2026-06-28

### Added
- **Zurücksetzen je Angebot**: Button löscht den kompletten Preisverlauf sowie
  Vergleichs-/Kalender-Cache und startet sofort eine frische Erstabfrage — das Tracking
  beginnt wieder bei „null". Das Angebot selbst (URL, Name, Wunschpreis) bleibt erhalten.

## [0.5.0] - 2026-06-28

### Added
- **Hotelbeschreibung als PDF**: Link je Angebot (öffnet das offizielle TUI-Hotel-PDF).
  Wird aus den Angebotsdaten gebaut und auch als HA-Sensor-Attribut `hotel_pdf` bereitgestellt.

### Changed
- **Preiskalender zeigt jetzt die volle buchbare Spanne** (heute bis ~12–14 Monate,
  inventarabhängig) statt nur des gewählten Zeitraums ±7 Tage — durch alle verfügbaren
  Monate blätterbar; der gewählte Zeitraum bleibt hervorgehoben.

## [0.4.1] - 2026-06-28

### Added
- **Ort/Region je Angebot** (z. B. „Playa del Ingles, Gran Canaria") — wird aus dem
  TUI-Breadcrumb gelesen, in der Karte unter dem Hotelnamen angezeigt, in die
  Schnellsuche aufgenommen und als HA-Sensor-Attribute ergänzt (`location`, `region`,
  `country`).

## [0.4.0] - 2026-06-28

### Added
- **Preiskalender** je Angebot (Button „Kalender"): Monats-Grid mit dem günstigsten
  Preis pro Abreisetag (wie auf tui.com). Markiert den günstigsten Termin (grün) und
  den günstigsten Termin **in deinem gewählten Zeitraum** sowie Tage außerhalb des
  Zeitraums (gedimmt); Monatsnavigation. Wird wie der Vergleich **gespeichert**
  (Zeitstempel + „Neu abfragen"). Respektiert alle Filter der Original-URL.

## [0.3.3] - 2026-06-28

### Fixed
- **Falscher Preis/falsche Verpflegung bei mehreren Verpflegungsarten**: Der
  JSON-Abruf übernahm nicht alle Filter der Original-URL — u. a. `boardTypes`,
  `operators`, `roomTypes`, `viewTypes` fehlten. Dadurch konnte die API ein anderes
  (billigeres) Angebot liefern, z. B. Halbpension statt „Alles Inklusive". Jetzt
  werden **alle Filter der Original-URL** durchgereicht, und die Verpflegungs-Codes
  werden korrekt ins API-Schema übersetzt (`AI` → `GT06-AI`).

## [0.3.2] - 2026-06-28

### Added
- **Schnellsuche**: Suchfeld über der Angebotsliste filtert die geladenen Angebote
  sofort nach Hotel, eigenem Namen, Ziel/Abflughafen und Reise-Details.

## [0.3.1] - 2026-06-28

### Changed
- **Pro-Person-Vergleich wird jetzt gespeichert** (in der Datenbank). Beim Öffnen
  wird das gespeicherte Ergebnis sofort angezeigt — kein unnötiger neuer Abruf mehr.
  Mit **Zeitstempel** („Abgefragt: …") und Button **„Neu abfragen"** für eine
  Aktualisierung auf Wunsch.

## [0.3.0] - 2026-06-28

### Changed
- **Preisabruf jetzt über die offene TUI-JSON-API** statt Seiten-Rendering — rund
  **0,5 s statt 30–60 s**, deutlich robuster (kein HTML-/Text-Parsing). Der
  Headless-Chromium-Scraper bleibt als **automatischer Fallback**, falls die API mal
  nicht erreichbar ist. Der eingegebene Reisezeitraum wird respektiert; getrackt wird
  das per `cheapest`-Flag markierte günstigste Angebot.
- Genauere Daten „gratis" aus der API: exakter Streichpreis/Rabatt, strukturierte
  Flüge (Datum/Zeit/Airline/Stopps/Route) und zuverlässige Verfügbarkeit.

### Added
- **Hotel-Sterne & HolidayCheck-Bewertung** (Ø-Note /6, Anzahl Bewertungen,
  Weiterempfehlung %) in der Karte und als HA-Sensor-Attribute (`stars`, `rating`,
  `rating_count`, `recommendation`).
- **„Kostenlos stornierbar"-Badge** (aus `cancellationType`) in der Karte und als
  Sensor-Attribut `cancellation`.

## [0.2.0] - 2026-06-28

### Added
- **Pro-Person-Vergleich**: Button „Vergleich" am Diagramm öffnet einen Live-Vergleich
  des Preises pro Person für die aktuelle Reisendenzahl gegenüber 2 Personen (bei
  aktuell 2 → 2 ↔ 1). Tabelle mit Preis p. P., Gesamt und Differenz; günstigster
  Preis pro Person grün hervorgehoben. Rein on-demand — nichts wird gespeichert.
- **Einzelzimmer-Riegel**: Bei Einzelzimmer-Angeboten („Einzelzimmer"/„Single Room")
  wird kein Vergleichs-Button angezeigt (2-Personen-Abruf nicht möglich).
- Robuster Vergleichs-Abruf: schlägt der feste Zimmercode für eine andere Belegung
  fehl, wird einmalig ohne `roomTypeOpCodes` erneut versucht.

## [0.1.6] - 2026-06-28

### Fixed
- **Neustart löste sofort eine Komplettabfrage aus**, auch wenn das Prüfintervall noch
  nicht erreicht war. Der Poller arbeitet jetzt **fälligkeitsbasiert**: ein Angebot
  wird erst wieder geprüft, wenn seit seinem letzten Check (über Neustarts hinweg) das
  Intervall verstrichen ist.

## [0.1.5] - 2026-06-28

### Added
- **Favicon** (TUI-Flugzeug-Icon) in Web-UI und Login-Seite.
- **AppArmor-Profil** (`apparmor.txt`, `tuiwatch_addon`) — schränkt das Add-on ein;
  Chromium-konform (inkl. `/dev/shm`).
- **Telegram-Startmeldung**: ist Telegram konfiguriert, kommt beim Start eine kurze
  Statusnachricht („TUIWatch gestartet — N Reisen geladen").

### Fixed
- **Preisdiagramme flackerten** alle paar Sekunden: das UI rendert jetzt nur noch bei
  tatsächlich geänderten Daten neu, statt bei jedem 5-Sekunden-Poll die Canvas neu zu
  zeichnen.

## [0.1.4] - 2026-06-27

### Added
- **Benachrichtigungen** bei Preisänderung und erreichtem Wunschpreis — über
  **Home Assistant** (persistent_notification) und/oder **Telegram** (Bot-Token +
  Chat-ID). Optionen: `notify_ha`, `notify_price_change`, `telegram_bot_token`,
  `telegram_chat_id`.
- **Wunschpreis (Zielpreis) pro Angebot** — im UI eingebbar; wird der Preis ≤ Wunsch,
  kommt eine Benachrichtigung. Auch als Sensor-Attribut `target_price`.
- **Statistik je Angebot**: niedrigster/höchster/Durchschnittspreis + „Bestpreis"-Badge
  (UI) sowie Sensor-Attribute `min_price`, `max_price`, `avg_price`.

### Changed
- **Robusterer Abruf**: bis zu 2 Versuche bei Fehlschlag; bestätigter Gesamtpreis nach
  Verfügbarkeitsprüfung; die Haupt-Angebotskarte wird zuverlässiger getroffen
  (keine „Empfehlungs"-Karte).

### Security
- Technische Exception-Texte werden nicht mehr im UI/Sensor angezeigt, sondern nur
  noch ins Log geschrieben (generische Meldung nach außen).

## [0.1.3] - 2026-06-27

### Changed
- **Getrackt wird jetzt der konkrete „Günstigster Preis"** (erste Angebotskarte,
  z. B. 1.978 €) statt des unverbindlichen „ab"-Lockpreises der Dein-Angebot-Box.
  Genauer und buchungsnah.

### Added
- **Flugdetails**: Hin- und Rückflug (Datum, Uhrzeit, Airline, Direkt/Umstieg)
  sowie Zimmer und Abflughafen werden ausgelesen, in der Karte angezeigt und als
  HA-Sensor-Attribute (`flight_outbound`, `flight_return`, `room`,
  `departure_airport`) gespeichert.
- **Verfügbarkeitsprüfung**: TUIWatch klickt „Verfügbarkeit prüfen" und erfasst,
  ob das Angebot verfügbar ist. Anzeige als Badge (✓/✗) und als HA-Sensor-Attribut
  `available` (true/false).

## [0.1.2] - 2026-06-27

### Added
- **Home-Assistant-Sensoren**: je Angebot ein Sensor `sensor.tuiwatch_<hotelname>`
  (bei gleichem Hotelnamen `_2`, `_3` …). Wert = aktueller Preis in €, bei Fehler
  `unavailable`. Attribute u. a. `description` (Reise-Eckdaten), `hotel`, `old_price`,
  `discount`, `last_checked`, `url`. Per Option `ha_sensors` abschaltbar.
  Verwaiste Sensoren werden automatisch entfernt.
- **Übersetzungen der Add-on-Konfiguration** (DE/EN) für die HA-Optionsseite.

## [0.1.1] - 2026-06-27

### Fixed
- **Konsole leer hinter Ingress**: Die Konsole hängte beim Aufruf von `/api/console`
  den Ingress-Pfad nicht an (G war nicht über `window` erreichbar) → 401, keine
  Ausgabe. `G` wird jetzt an `window` gehängt, sodass der korrekte Ingress-Pfad
  verwendet wird.

## [0.1.0] - 2026-06-27

### Added
- Erste Version: **TUIWatch — Reisepreis-Tracker** für TUI-Pauschalreisen
- Beliebig viele TUI-Angebots-URLs verfolgen (URL von tui.com einfügen)
- Preis-Auslesen per Headless-Chromium (Playwright) — liest die „Dein Angebot"-Box
- Speichert den Preisverlauf in SQLite und zeigt ihn als Diagramm
- Anzeige von aktuellem Preis, Vergleichspreis, Rabatt und **Delta** (gestiegen/gefallen)
- Automatischer Hotelname (`Riu Papayas`) und Reise-Eckdaten als Beschreibung
- Periodische Prüfung (Standard alle 6 h) + manuelles „Prüfen" / „Alle prüfen"
- Versteckte Konsole per Doppelklick auf das Logo (Hintergrund-Logs)
- Login-Schutz beim Direktzugriff; hinter HA-Ingress automatisch authentifiziert
- Oberfläche auf Deutsch
