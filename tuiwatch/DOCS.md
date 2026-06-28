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

## Hotels suchen

Statt einzelne Hotels von Hand einzufügen, kannst du über **🔍 Hotels suchen** eine
ganze **Region** durchsuchen:

1. Auf tui.com **zuerst eine Region/ein Ziel** wählen (z. B. „Kapverdische Inseln") und
   Datum, Personen & Abflughafen setzen.
2. Die **Ergebnis-URL** (enthält `regionGiataIds=…`) kopieren und in TUIWatch unter
   „Hotels suchen" einfügen.
3. Optional die Filter setzen: **nur Veranstalter TUI**, **Verpflegung** (AI/HP/VP/
   Frühstück), **Sterne ≥** und **Weiterempfehlung ≥ %** → **Suchen**.

Du bekommst eine Trefferliste mit Hotelname, Sternen, Ort, **HolidayCheck-
Weiterempfehlung**, Verpflegung, Nächten und **Preis pro Person**. Je Treffer:
**Tracken** (übernimmt das Hotel ins Tracking) oder **Öffnen** (auf tui.com). Mit
**Alle tracken** werden alle angezeigten Treffer auf einmal übernommen. Der Abflughafen
kommt aus der eingefügten URL.

Für jedes Angebot werden angezeigt: Hotelname, **Ort/Region** (z. B. „Playa del
Ingles, Gran Canaria"; Klick öffnet Google Maps), **Sterne & HolidayCheck-Bewertung**,
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
- **Günstigerer-Termin-Alarm** (`notify_cheaper_date`): meldet, wenn der Preiskalender
  einen anderen Abreisetag deutlich günstiger zeigt (Schwelle `cheaper_date_min_diff`).
- **Ausverkauft-/Fehler-Alarm** (`notify_errors`): meldet, wenn ein Angebot mehrmals in
  Folge kein Ergebnis liefert, und gibt Entwarnung, sobald es wieder klappt.
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

## Nächte-Vergleich

Der Button **Nächte** öffnet einen Dialog, in dem sich per **− / +** eine Spanne
einstellen lässt (Standard 3, max ±7). TUIWatch fragt dann live die Preise für
**kürzere und längere Reisedauern** ab — bei z. B. 10 Nächten also 7–9 und 11–13 — und
zeigt eine Tabelle mit **Preis pro Person**, **€ pro Nacht**, **Gesamtpreis** und der
**Differenz pro Person** zur aktuellen Dauer. Die günstigste Zeile wird grün
hervorgehoben, die aktuell getrackte Dauer ist als „aktuell" markiert. Nicht an jedem
Tag gibt es Flüge — Dauern ohne Angebot erscheinen als „nicht abrufbar". Das Ergebnis
wird **gespeichert** (Zeitstempel + **„Neu abfragen"**).

## Preiskalender

Der Button **Kalender** je Angebot zeigt ein Monats-Raster mit dem günstigsten Preis
pro Abreisetag (ab/Person) — wie der Preiskalender auf tui.com. Hervorgehoben werden
der **günstigste Termin insgesamt** (grün) und der **günstigste Termin in deinem
gewählten Zeitraum**; Tage außerhalb deines Zeitraums sind gedimmt. Die Tage sind als
**Heatmap** eingefärbt (grün = günstig, rot = teuer); ein **Klick auf einen Tag öffnet
genau diesen Termin auf tui.com**, ein **Rechtsklick speichert den Termin als neues,
eigenständiges Angebot** (mit fixiertem Datum) und prüft ihn sofort. Es wird die
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
  `discount`, `total_price`, `travellers`, `min_price`, `max_price`, `avg_price`,
  `target_price`, `hotel_pdf`, `last_checked`, `url`

## Bedienung

- **Als E-Mail senden** — verschickt alle Angebote als HTML-Mail (Empfänger wird vorher abgefragt; benötigt SMTP-Optionen).
- **Backup / Wiederherstellen** — getrackte Angebote als JSON sichern bzw. importieren.
- **Übersicht** über der Liste: Anzahl, günstigstes Angebot, Anzahl unter Wunschpreis.
- **Suchfeld** — filtert die geladenen Angebote sofort nach Hotel, Name, Ort, Ziel/Abflughafen und Details.
- **Sortierung** — Liste nach Hinzugefügt, Preis, größter Preisänderung, Bewertung oder Name ordnen.
- **Umbenennen** (✎ neben dem Namen) — eigenen Namen vergeben; leer = Hotelname.
- **Prüfen** — ein Angebot sofort neu abfragen.
- **Alle prüfen** — alle Angebote abfragen.
- **Verlauf** — Diagramm + Tabelle der gesamten Preishistorie, inkl. **CSV-Export**.
- **Nächte** — Preise für kürzere/längere Reisedauern (Basis ±N) live vergleichen.
- **Pausieren / Fortsetzen** — setzt die automatische Prüfung für ein Angebot aus, ohne es zu löschen.
- **Zurücksetzen** — löscht den Preisverlauf (und Vergleichs-/Kalender-Cache) und beginnt nach einer frischen Abfrage wieder bei „null". Angebot, Name und Wunschpreis bleiben.
- **Archivieren / Reaktivieren** — legt ein Angebot ins Archiv (keine Live-Abfragen mehr) bzw. holt es zurück. Reisen werden **automatisch archiviert**, sobald ihr Rückreisedatum vergangen ist; manuell z. B. wenn ein Angebot ausgebucht/nicht mehr verfügbar ist. Archivierte Angebote sind über den Schalter **„Archiv"** oben einblendbar und werden bei Prüfungen, Übersicht und E-Mail-Versand ausgenommen.

Bei mehreren Reisenden wird zusätzlich zum **Preis pro Person** der **Gesamtpreis**
angezeigt. TUIWatch ist außerdem als **PWA installierbar** (Manifest + Service Worker;
am besten über Direktzugriff/Reverse-Proxy nutzen).
- **Löschen** — Angebot inkl. Verlauf entfernen.
- **Doppelklick auf das Logo** — Konsole mit Hintergrund-Logs ein/aus.

## Daten

Alles wird unter `/data/tuiwatch.db` (SQLite) gespeichert und bleibt über
Neustarts erhalten.

## Technik / Wartung

Der Preis wird mit Headless-Chromium (Playwright) ausgelesen. Wenn TUI das Layout
ändert und Abrufe mit „nicht gefunden" fehlschlagen, hilft die Anleitung in
[SCRAPING.md](SCRAPING.md), die Selektoren neu zu bestimmen.
