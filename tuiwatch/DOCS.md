# TUIWatch

Reisepreis-Tracker für TUI-Pauschalreisen. Verfolgt den Preis konkreter
Angebots-URLs und zeigt den Verlauf mit Hoch/Runter-Anzeige.

## Installation

1. Add-on installieren und starten.
2. Über **OPEN WEB UI** (Ingress) öffnen oder direkt über Port `17794`.
3. Beim Direktzugriff mit `username`/`password` aus der Konfiguration anmelden.

## Konfiguration

```yaml
username: admin          # Login (Direktzugriff)
password: secret         # bitte ändern!
session_hours: 24        # Dauer der Anmeldung
poll_interval: 21600     # Prüfintervall in Sekunden (6 h); Minimum 600
verbose_log: false       # ausführliche Logs
```

## Reise hinzufügen

1. Auf tui.com die Reise mit Datum, Personen und Abflughafen suchen.
2. Die URL der Angebotsseite kopieren (Format:
   `https://www.tui.com/pauschalreisen/suchen/angebote/<Hotel>/<id>/offer/?...`).
3. Im Web-UI einfügen → **Hinzufügen**. Der erste Preis wird sofort geprüft.

Für jedes Angebot werden angezeigt: Hotelname, **Ort/Region** (z. B. „Playa del
Ingles, Gran Canaria"), **Sterne & HolidayCheck-Bewertung**,
Reise-Eckdaten (Nächte, Zimmer, Verpflegung), **Hin- und Rückflug**
(Datum/Uhrzeit/Airline/Direkt), der konkrete **„Günstigster Preis"** (buchbar),
durchgestrichener Vergleichspreis + Rabatt, **Verfügbarkeit** (✓/✗),
ggf. **„kostenlos stornierbar"**, ein Link zur **Hotelbeschreibung als PDF**,
Veränderung zum letzten Check und ein Preisverlauf-Diagramm (Klick auf **Verlauf**
für die volle Historie).

> Der Preis wird seit v0.3.0 direkt aus der TUI-JSON-API gelesen (schnell und
> robust); bei Störungen schaltet TUIWatch automatisch auf das langsamere
> Browser-Auslesen um. Details: [SCRAPING.md](SCRAPING.md).

> Getrackt wird der konkrete, buchbare Preis der günstigsten Angebotskarte — nicht
> der unverbindliche „ab"-Lockpreis.

## Wunschpreis & Benachrichtigungen

- Pro Angebot kannst du im UI einen **Wunschpreis** setzen. Fällt der Preis auf
  oder unter diesen Wert, wirst du benachrichtigt.
- Bei **jeder Preisänderung** (steigt/fällt) kommt ebenfalls eine Meldung
  (abschaltbar über `notify_price_change`).
- Kanäle:
  - **Home Assistant**: persistente Benachrichtigung (Option `notify_ha`, Standard an).
  - **Telegram**: `telegram_bot_token` + `telegram_chat_id` setzen (Bot via @BotFather,
    Chat-ID via @userinfobot). Ist Telegram aktiv, kommt beim Start des Add-ons eine
    kurze Statusmeldung („TUIWatch gestartet — N Reisen geladen").

## Pro-Person-Vergleich

Am Diagramm jedes Angebots gibt es den Button **Vergleich**. Er fragt das Angebot
live für die aktuell getrackte Reisendenzahl **und** für 2 Personen ab (ist es bereits
für 2, wird gegen 1 verglichen) und zeigt eine Tabelle mit **Preis pro Person**,
**Gesamtpreis** und der **Differenz pro Person** — für 2 Personen ist der Preis pro
Person oft günstiger (kein Einzelzimmer-Zuschlag). Der günstigste Preis pro Person wird
grün hervorgehoben.

Das Ergebnis wird **gespeichert**: Beim erneuten Öffnen erscheint sofort der letzte
Vergleich mit **Zeitstempel** („Abgefragt: …") — ohne neuen Abruf. Über **„Neu
abfragen"** lässt sich der Vergleich bei Bedarf aktualisieren. Bei
**Einzelzimmer**-Angeboten erscheint kein Vergleichs-Button, da ein 2-Personen-Abruf
nicht möglich ist.

## Preiskalender

Der Button **Kalender** je Angebot zeigt ein Monats-Raster mit dem günstigsten Preis
pro Abreisetag (ab/Person) — wie der Preiskalender auf tui.com. Hervorgehoben werden
der **günstigste Termin insgesamt** (grün) und der **günstigste Termin in deinem
gewählten Zeitraum**; Tage außerhalb deines Zeitraums sind gedimmt. Es wird die
**volle buchbare Spanne** angezeigt (heute bis ~12–14 Monate, je nach Verfügbarkeit);
mit den Pfeilen blätterst du durch die Monate. Das Ergebnis wird **gespeichert** (Zeitstempel + „Neu
abfragen") und respektiert alle Filter deiner Angebots-URL (Verpflegung, Veranstalter,
Zimmer, Abflughafen).

## Home-Assistant-Sensoren

Bei aktiver Option `ha_sensors` legt TUIWatch je Angebot einen Sensor
`sensor.tuiwatch_<hotelname>` an (bei gleichem Hotel `_2`, `_3` …):
- **Wert** = aktueller Preis in € (bei Fehler `unavailable`)
- **Attribute**: `description`, `hotel`, `location`, `region`, `country`, `room`,
  `departure_airport`,
  `flight_outbound`, `flight_return`, `available` (true/false), `cancellation`,
  `stars`, `rating`, `rating_count`, `recommendation`, `old_price`,
  `discount`, `min_price`, `max_price`, `avg_price`, `target_price`,
  `last_checked`, `url`

## Bedienung

- **Suchfeld** — filtert die geladenen Angebote sofort nach Hotel, Name, Ziel/Abflughafen und Details.
- **Prüfen** — ein Angebot sofort neu abfragen.
- **Alle prüfen** — alle Angebote abfragen.
- **Verlauf** — Diagramm + Tabelle der gesamten Preishistorie.
- **Zurücksetzen** — löscht den Preisverlauf (und Vergleichs-/Kalender-Cache) und beginnt nach einer frischen Abfrage wieder bei „null". Angebot, Name und Wunschpreis bleiben.
- **Löschen** — Angebot inkl. Verlauf entfernen.
- **Doppelklick auf das Logo** — Konsole mit Hintergrund-Logs ein/aus.

## Daten

Alles wird unter `/data/tuiwatch.db` (SQLite) gespeichert und bleibt über
Neustarts erhalten.

## Technik / Wartung

Der Preis wird mit Headless-Chromium (Playwright) ausgelesen. Wenn TUI das Layout
ändert und Abrufe mit „nicht gefunden" fehlschlagen, hilft die Anleitung in
[SCRAPING.md](SCRAPING.md), die Selektoren neu zu bestimmen.
