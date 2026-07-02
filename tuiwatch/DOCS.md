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
notify_api_errors: true  # Alarm, wenn eine TUI-API gestört ist
notify_booked_drop: true # Alarm, wenn Preis unter den gebuchten Preis fällt
booked_drop_min_diff: 50 # Mindest-Ersparnis dafür (€)
digest_enabled: false    # wöchentlicher Überblick (Telegram/E-Mail)
digest_weekday: 1        # Versandtag (1 = Mo … 7 = So)
verbose_log: false       # ausführliche Logs
```

## Reise hinzufügen

1. Auf tui.com die Reise mit Datum, Personen und Abflughafen suchen.
2. Die URL der Angebotsseite kopieren (Format:
   `https://www.tui.com/pauschalreisen/suchen/angebote/<Hotel>/<id>/offer/?...`).
3. Im Web-UI einfügen → **Hinzufügen**. Der erste Preis wird sofort geprüft.

## Hotels suchen

Über **🔍 Hotels suchen** kannst du eine ganze **Region** durchsuchen — auf drei Wegen:

**1. Suchmaske (empfohlen, ohne URL):**
- **Reiseziel** über den Picker wählen — Drilldown **Land → Region → Insel** (z. B.
  Spanien → Kanarische Inseln → Gran Canaria); „Ganze Region wählen" auf jeder Ebene.
  Das **Suchfeld** durchsucht **alle Ebenen** auf einmal: Tippst du z. B. „Kanarische
  Inseln", erscheint das Ziel direkt (mit Pfad „— Spanien › Kanarische Inseln"), ohne erst
  Spanien öffnen zu müssen. (Grundlage ist ein Reiseziel-Index, der beim Start im
  Hintergrund aufgebaut und in der Datenbank zwischengespeichert wird.)
- **Abflughafen** (TUI-Liste, zuletzt genutzter wird gemerkt), **Zeitraum von–bis** +
  **Nächte**, **Reisende**.
- **Exakt** (neben „Nächte"): sucht Reisen mit einer Dauer, die **genau dem gewählten
  Zeitraum** entspricht (TUI-nativ `duration=exact`; z. B. 01.07.–05.07. → 4 Nächte).
  Bei aktivem Häkchen bestimmt TUI die Dauer, das Nächte-Feld ist gesperrt und zeigt zur
  Info die Tagesdifferenz.
- **Nächte-Hinweis**: passt die eingegebene Nächtezahl nicht in den Zeitraum
  (z. B. 01.07.–03.07. mit 5 Nächten), erscheint ein Hinweis (die Suche läuft trotzdem).
- **Reset** setzt die komplette Suchmaske (inkl. Reiseziel, Abflughafen, Datum, Nächte,
  Reisende und Filter) wieder auf die Standardwerte zurück.
- **Fluggesellschaften** (optional): Dropdown mit Mehrfachauswahl — leer = alle. Die
  Auswahl fließt in die Suche **und** in das getrackte Angebot (Preis nur mit diesen
  Airlines).
- Filter: **TUI** (nur Veranstalter TUI Deutschland; aus = alle), **Nur Direktflug**,
  **Verpflegung** (AI/HP/VP/Frühstück/Ohne — Mehrfachauswahl, jeweils inkl. „Plus"-Variante
  bzw. „laut Programm"), **Sterne ≥** (Standard 3), **Weiterempfehlung ≥ %**
  (Standard 80) → **Suchen**.
- **Gespeicherte Suchen:** die kompletten Eingaben unter einem Namen speichern
  („★ Speichern") und später aus dem Dropdown wieder laden — für wiederkehrende Suchen.
  Eine geladene Suche kannst du nach Anpassungen mit **„💾 Änderungen speichern"** ohne
  erneute Namenseingabe überschreiben. Sie liegen in der Add-on-Datenbank und sind damit
  **geräteübergreifend** verfügbar (gleiche Liste auf Handy, Tablet, PC).

**2. Aus einem Angebot:** Bei jedem aktiven Angebot der Button **Region** sucht **weitere
Hotels derselben Region** für dieselben Reisedaten/Dauer/Reisende/Abflughafen; Veranstalter
und Verpflegung werden aus dem Angebot vorbelegt.

**3. TUI-URL einfügen:** Unter „Alternativ: TUI-Such-URL einfügen" eine Ergebnis-URL von
tui.com (mit `regionGiataIds=…`) einfügen.

Die Trefferliste zeigt Hotelname, Sterne, Ort, **HolidayCheck-Weiterempfehlung**,
Verpflegung, Nächte und **Preis pro Person**; **sortierbar** nach Preis, Preis/Nacht,
Weiterempfehlung oder Sternen und über ein **Suchfeld** nach Name/Ort/Verpflegung
filterbar. Je Treffer **Tracken** oder **Öffnen** (tui.com), dazu **Alle tracken**.
Nach dem **Tracken** öffnet sich direkt die **Zimmerauswahl** des neuen Angebots.
Bereits **aktiv** getrackte Hotels sind mit „✓ getrackt" markiert (archivierte zählen
nicht). Der **Tracken**-Button bleibt aber nutzbar: Dasselbe Hotel kann **mehrfach** mit
**unterschiedlichen Suchparametern** (z. B. anderer Zeitraum) verfolgt werden; nur exakt
identische Angebote werden abgelehnt.

Für jedes Angebot werden angezeigt: ein **Hotelbild** (sofern ermittelbar), Hotelname,
**Ort/Region** (z. B. „Playa del
Ingles, Gran Canaria"; Klick öffnet Google Maps), **Sterne & HolidayCheck-Bewertung**
(Klick öffnet die HolidayCheck-Bewertungen zum Hotel via Google `site:holidaycheck.de`),
Reise-Eckdaten (Nächte, Zimmer, Verpflegung), **Hin- und Rückflug**
(Datum/Uhrzeit/Airline + **Flugnummer**/Direkt), der konkrete **„Günstigster Preis"**
(buchbar), durchgestrichener Vergleichspreis + Rabatt, **Verfügbarkeit** (✓/✗),
ggf. **„kostenlos stornierbar"**, die **Buchungscodes** (TUI-Buchungscode,
Zimmer-Buchungscode, GIATA-Hotel-ID — zum Buchen/Anrufen bei TUI; auch in der E-Mail),
ein Link zur **Hotelbeschreibung als PDF**,
die Veränderung zum letzten Check sowie der **Trend**. Den **Preisverlauf** zeigt der
Button **Verlauf** (Diagramm auf den Verlauf gezoomt + volle Historie als Tabelle). Im
Diagramm markieren **Fähnchen** wichtige Änderungen (Zimmerwechsel, gebuchter Preis,
Wunschpreis, Zurücksetzen) — mit **Mouseover** erscheint Datum + Beschreibung.

> Der Preis wird seit v0.3.0 direkt aus der TUI-JSON-API gelesen (schnell und
> robust); bei Störungen schaltet TUIWatch automatisch auf das langsamere
> Browser-Auslesen um. Details: [SCRAPING.md](SCRAPING.md).

> Getrackt wird der konkrete, buchbare Preis der günstigsten Angebotskarte — nicht
> der unverbindliche „ab"-Lockpreis.

## Meine Reisen (gebuchte Reisen / PDF-Import)

Über **🧳 Meine Reisen** verwaltest du deine **gebuchten** TUI-Reisen — getrennt vom
Preis-Tracking, als dauerhaftes Archiv (Vergangenheit und Zukunft).

- **Import:** Eine **TUI-Reisebestätigung als PDF** auswählen oder per **Drag & Drop** in den
  Import-Bereich ziehen. TUIWatch liest die Eckdaten automatisch aus: Buchungsnummer,
  Reisende (1–7), Hotel + Reiseziel, Zeitraum/Nächte, Verpflegung, Hin-/Rückflug
  (inkl. Airline & Flugnummer), Extras (Sitzplatz, Handgepäck, Flex Tarif, Bustransfer),
  Rabatte/Coupons, Zahlungsart sowie Gesamt-, Paket- und Pro-Nacht-Preis.
- **PDF bleibt gespeichert:** Die Original-PDF wird dauerhaft unter `/data/trips` abgelegt
  und ist je Reise über **„PDF"** wieder **abrufbar** (öffnen/herunterladen).
- **Liste & Detail:** Alle Reisen nach Reisebeginn sortiert; je Reise auch der
  **Reisepreis pro Nacht** (Hotel/Flug/Transfer **nach Rabatt, ohne Extras**). Klick auf
  **„Details"** zeigt die komplette Aufschlüsselung inkl. Flügen, Extras, Zahlungen sowie
  **€/Nacht** und **€/Person/Nacht** (Reisepreis und gesamt).
- **Statistik:** Anzahl Reisen, Summe Nächte, **Gesamtausgaben** (Summe aller Reisepreise
  inkl. Extras), **Eigene Kosten** (je Reise Gesamtpreis geteilt durch die Anzahl
  Reisende, aufsummiert = dein persönlicher Anteil) und **Ø €/Nacht pro Person** — gesamt
  **und pro Reisejahr** aufgeschlüsselt. Der €/Nacht-Wert ist durchweg **pro Person**
  (Personen-Nächte = Nächte × Reisende), damit Solo- und Gruppenreisen vergleichbar sind.
- **Aktualisieren/Löschen:** Ein erneuter Import derselben Buchungsnummer **überschreibt**
  den vorhandenen Eintrag (kein Duplikat). **„Löschen"** entfernt die Reise inkl. der
  gespeicherten PDF.

> Datenschutz: Die PDFs und ausgelesenen Daten bleiben **lokal** im Add-on (Ordner
> `/data/trips` bzw. die Add-on-Datenbank) — es werden keine Daten nach außen gesendet.
> Der PDF-Parser steckt im eigenen Modul `tripparser.py` und ist auf die bekannten
> TUI-Layout-Varianten ausgelegt; bei unbekannten Formaten kann der Import abweichen.

## Wunschpreis & Benachrichtigungen

- Pro Angebot kannst du im UI einen **Wunschpreis** setzen. Fällt der Preis auf
  oder unter diesen Wert, wirst du benachrichtigt.
- Bei **jeder Preisänderung** (steigt/fällt) kommt ebenfalls eine Meldung
  (abschaltbar über `notify_price_change`).
- **Günstigerer-Termin-Alarm** (`notify_cheaper_date`): meldet, wenn der Preiskalender
  einen anderen Abreisetag deutlich günstiger zeigt (Schwelle `cheaper_date_min_diff`).
  Die Meldung kommt nur bei einem **wirklich neuen Tiefstwert** (anderer Termin oder
  nochmals tieferer Preis) — nicht bei jeder Prüfung — und übersteht Neustarts. Zum
  Abschalten `notify_cheaper_date: false` setzen.
- **Ausverkauft-/Fehler-Alarm** (`notify_errors`): meldet, wenn ein Angebot mehrmals in
  Folge kein Ergebnis liefert, und gibt Entwarnung, sobald es wieder klappt.
- **API-Ausfall-Alarm** (`notify_api_errors`): meldet, wenn der API-Selbsttest einen
  kritischen TUI-Endpunkt als gestört erkennt (TUI hat evtl. die API geändert), und gibt
  Entwarnung, sobald wieder alles läuft.
- **„Günstiger als gebucht"-Alarm** (`notify_booked_drop`): hast du bei einem Angebot
  deinen **gebuchten Preis** hinterlegt, meldet TUIWatch, wenn der Preis später deutlich
  darunter fällt (Schwelle `booked_drop_min_diff`, Standard 50 €) — Umbuchen könnte sich
  lohnen. Meldet nur bei neuen Tiefstwerten (kein Spam), neustart-fest.
- **Wochenüberblick / Digest** (`digest_enabled`): optionale wöchentliche Zusammenfassung
  (größte Rückgänge, neue Tiefstwerte, Angebote unter Wunschpreis) per Telegram und/oder
  E-Mail. `digest_weekday` legt den Wochentag fest (1 = Montag … 7 = Sonntag); war das
  Add-on am Stichtag aus, wird der Versand später in der Woche nachgeholt. Sofort testen
  über den Button **„📊 Wochenüberblick"**.
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
pro Abreisetag (ab/Person) — wie der Preiskalender auf tui.com. Er **öffnet direkt im
Reisemonat** deines Angebots. Hervorgehoben werden der **günstigste Termin insgesamt**
(grün, mit **🐷 Sparschwein-Icon**) und der **günstigste Termin in deinem gewählten
Zeitraum**; Tage außerhalb deines
Zeitraums sind gedimmt. Die Tage sind als **Heatmap** eingefärbt (grün = günstig, rot =
teuer); ein **Klick auf einen Tag öffnet genau diesen Termin auf tui.com**, ein
**Rechtsklick speichert den Termin als neues, eigenständiges Angebot** (mit fixiertem
Datum) und prüft ihn sofort. Der Kalender deckt die **volle Spanne vom aktuellen Monat
bis über den Reisezeitraum hinaus** ab: mit den Pfeilen blätterst du zurück bis zum
aktuellen Monat und vor bis zum Ende des buchbaren Inventars. (Die TUI-Kalender-API
liefert pro Abruf nur ein begrenztes Fenster; TUIWatch fügt daher wie die TUI-Seite
mehrere Abrufe zu einer durchgehenden Zeitleiste zusammen.) Das Ergebnis wird
**gespeichert** (Zeitstempel + „Neu abfragen") und respektiert alle Filter deiner
Angebots-URL (Verpflegung, Veranstalter, Zimmer, Abflughafen).

## TUI-Aktionscodes

Über **🎟 Aktionscodes** überwacht TUIWatch die **öffentlichen** Aktionscodes von
tui.com (`/aktionscode/`) — **ohne Login** — und benachrichtigt dich bei **neuen** Codes
(Telegram/HA). Es gibt nicht immer welche; sind keine da, kommt auch keine Meldung.

- **Anzeige:** aktuell aktive Codes mit **Wert** (z. B. 150/250/300 €), dazu **buchbar
  bis** und **Reisezeitraum**. Erfasst werden die myTUI-Codes (`ACMYTUI…`) und die
  Codes **ohne Konto** (`SAVE…`).
- **Ablauf:** rein serverseitig per Abruf der Aktionscode-Seite (kein Browser, kein Login,
  kein Captcha). Prüfintervall `aktionscode_interval` (Standard 6 h); manuell über **„Jetzt
  prüfen"** im Aktionscode-Fenster.
- **Alarm:** nur bei **neu erschienenen** Codes (Dedup nach Wert, damit der tägliche
  Datumswechsel im Code kein Spam auslöst; eine später wiederkehrende Aktion meldet erneut).
- **Optionen:** `notify_aktionscodes` (Alarm an/aus), `aktionscode_min` (nur ab diesem
  Wert melden, Standard 0 = alle), `aktionscode_interval` (Prüfintervall in Sekunden).

## Home-Assistant-Sensoren

Bei aktiver Option `ha_sensors` legt TUIWatch je Angebot einen Sensor
`sensor.tuiwatch_<hotelname>` an (bei gleichem Hotel `_2`, `_3` …):
- **Wert** = aktueller Preis in € (bei Fehler `unavailable`)
- **Attribute**: `description`, `hotel`, `location`, `region`, `country`, `room`,
  `departure_airport`,
  `flight_outbound`, `flight_return`, `available` (true/false), `cancellation`,
  `stars`, `rating`, `rating_count`, `recommendation`, `old_price`,
  `discount`, `total_price`, `travellers`, `min_price`, `max_price`, `avg_price`,
  `target_price`, `booked_price`, `booked_diff` (Preis − gebucht), `image`,
  `booking_code`, `room_booking_code`, `hotel_pdf`, `last_checked`, `url`

## Bedienung

- **Als E-Mail senden** — verschickt alle Angebote als HTML-Mail (Empfänger wird vorher abgefragt; benötigt SMTP-Optionen).
- **Backup / Wiederherstellen** — **komplettes** Backup als **ZIP**: alle getrackten
  Angebote **inkl. Preisverlauf** und Diagramm-Markern, **„Meine Reisen" inkl. der
  Original-PDFs** sowie die **gespeicherten Suchen**. Die Wiederherstellung liest die ZIP
  (das alte reine JSON wird weiterhin akzeptiert) und arbeitet **nicht-destruktiv**:
  Fehlendes wird ergänzt, Bestehendes bleibt erhalten (Abgleich per URL, Buchungsnummer
  bzw. Name) — nichts wird gelöscht oder doppelt angelegt. (Reine Caches wie
  Vergleich/Kalender werden nicht gesichert, sie entstehen automatisch neu.)
- **Gebuchter Preis** — pro Angebot den **tatsächlich gezahlten Preis** hinterlegen
  (Feld „📌 Gebuchter Preis"). Das Tracking läuft weiter; angezeigt wird „seit Buchung
  ±X €" und im Diagramm eine eigene Linie. Fällt der Preis deutlich darunter, kommt
  (falls `notify_booked_drop` an) eine Benachrichtigung.
- **Übersicht** über der Liste: Anzahl, günstigstes Angebot, Anzahl unter Wunschpreis.
- **Suchfeld** — filtert die geladenen Angebote sofort nach Hotel, Name, Ort, Ziel/Abflughafen und Details.
- **Sortierung** — Liste nach Hinzugefügt, **Reisebeginn**, Preis, größter Preisänderung, Bewertung oder Name ordnen.
- **Sammelaktionen** — Angebote per Checkbox auswählen; in der erscheinenden Leiste lassen sich die ausgewählten gemeinsam **prüfen, als E-Mail senden, archivieren oder löschen** (E-Mail fragt den Empfänger ab und sendet nur die markierten aktiven Angebote).
- **Trend-Hinweis** — je Angebot zeigt ein kleines Badge die Tendenz aus dem bisherigen Verlauf (↘ fällt / ↗ steigt / → stabil).
- **Umbenennen** (✎ neben dem Namen) — eigenen Namen vergeben; leer = Hotelname.
- **Prüfen** — ein Angebot sofort neu abfragen.
- **Alle prüfen** — alle Angebote abfragen.
- **Verlauf** — Diagramm + Tabelle der gesamten Preishistorie, inkl. **CSV-Export**.
- **Nächte** — Preise für kürzere/längere Reisedauern (Basis ±N) live vergleichen.
- **Zimmer** — die wählbaren **Zimmerkategorien** des Hotels mit Preis pro Person und
  Aufpreis zum günstigsten anzeigen. Standardmäßig wird das **günstigste** Zimmer
  verfolgt; per **„tracken"** lässt sich eine bestimmte Kategorie fixieren („für ein paar
  Euro mehr was Besseres"), ab dann wird deren Preis verfolgt. **„Details ↗"** öffnet das
  Zimmer mit Fotos/Beschreibung auf tui.com; **„Günstigstes automatisch"** hebt die
  Festlegung wieder auf.
- **Pausieren / Fortsetzen** — setzt die automatische Prüfung für ein Angebot aus, ohne es zu löschen.
- **Zurücksetzen** — löscht den Preisverlauf (und Vergleichs-/Kalender-Cache) und beginnt nach einer frischen Abfrage wieder bei „null". Angebot, Name und Wunschpreis bleiben.
- **Archivieren / Reaktivieren** — legt ein Angebot ins Archiv (keine Live-Abfragen mehr) bzw. holt es zurück. Reisen werden **automatisch archiviert**, sobald ihr Rückreisedatum vergangen ist; manuell z. B. wenn ein Angebot ausgebucht/nicht mehr verfügbar ist. Archivierte Angebote sind über den Schalter **„Archiv"** oben einblendbar und werden bei Prüfungen, Übersicht und E-Mail-Versand ausgenommen.

Bei mehreren Reisenden wird zusätzlich zum **Preis pro Person** der **Gesamtpreis**
angezeigt. TUIWatch ist außerdem als **PWA installierbar** (Manifest + Service Worker;
am besten über Direktzugriff/Reverse-Proxy nutzen).
- **Löschen** — Angebot inkl. Verlauf entfernen.
- **Doppelklick auf das Logo** — Konsole mit Hintergrund-Logs ein/aus.

## API-Status / Selbsttest

TUIWatch liest die Preise über offene TUI-JSON-APIs (siehe [SCRAPING.md](SCRAPING.md)).
Beim **Start des Add-ons** und jederzeit **manuell** wird geprüft, ob diese Endpunkte
noch erreichbar sind und erwartungsgemäß antworten (Preis/Angebot, Hotelsuche,
Reiseziele, Abflughäfen, Preiskalender, Bewertung, Breadcrumb). Der Status steht im
**Footer** als Ampel: **grün** = alles ok, **gelb** = unkritische Hinweise, **rot** =
ein kritischer Endpunkt antwortet nicht. Ein Klick öffnet die Detailliste mit „Erneut
prüfen". So lässt sich schnell unterscheiden, ob ein fehlender Preis am Angebot liegt
oder TUI eine API geändert hat.

## Daten

Alles wird unter `/data/tuiwatch.db` (SQLite) gespeichert und bleibt über
Neustarts erhalten.

## Technik / Wartung

Der Preis wird primär direkt aus den offenen TUI-JSON-APIs gelesen; nur bei Störungen
schaltet TUIWatch automatisch auf das Auslesen per Headless-Chromium (Playwright) um.
Wenn TUI die APIs bzw. das Seitenlayout ändert und Abrufe fehlschlagen, hilft die
Anleitung in [SCRAPING.md](SCRAPING.md), die Endpunkte/Selektoren neu zu bestimmen.

**Regressionstests:** Unter `tests/` liegen Offline-Tests (pytest), die gegen echte,
reduzierte TUI-API-Antworten prüfen, dass die Auswertung der Antworten korrekt bleibt —
so fällt ein TUI-Formatwechsel schnell auf. Ausführen: `pip install -r
tests/requirements.txt` und dann `pytest tests/` im Ordner `tuiwatch/`. Details:
[tests/README.md](tests/README.md).
