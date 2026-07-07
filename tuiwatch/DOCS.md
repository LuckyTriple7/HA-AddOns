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
anthropic_api_key: ""    # Anthropic API-Key, aktiviert das KI-Fazit (leer = aus)
anthropic_model: claude-opus-4-8  # oder claude-sonnet-5 / claude-haiku-4-5 / claude-fable-5
ai_provider: anthropic   # oder gemini (gilt fuer ALLE KI-Features)
gemini_api_key: ""       # nur relevant bei ai_provider: gemini
gemini_model: gemini-3.1-pro  # oder gemini-3.5-flash / gemini-2.5-flash
ai_max_web_searches: 12  # Limit Websuchen/Aufruf, gilt nur bei Anthropic
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
  **Nur Erwachsene** (Adults-Only-Hotels), **Verpflegung** (AI/HP/VP/Frühstück/Ohne —
  Mehrfachauswahl, jeweils inkl. „Plus"-Variante bzw. „laut Programm"), **Lage**
  (Direkt am Strand, Sandstrand, Strand < 500m, Meerseite, Ruhig, Außerhalb —
  Mehrfachauswahl, schränkt weiter ein), **Sterne ≥** (Standard 3),
  **Weiterempfehlung ≥ %** (Standard 80) → **Suchen**.
- **Gespeicherte Suchen:** die kompletten Eingaben unter einem Namen speichern
  („★ Speichern") und später aus dem Dropdown wieder laden — für wiederkehrende Suchen.
  Eine geladene Suche kannst du nach Anpassungen mit **„💾 Änderungen speichern"** ohne
  erneute Namenseingabe überschreiben. Sie liegen in der Add-on-Datenbank und sind damit
  **geräteübergreifend** verfügbar (gleiche Liste auf Handy, Tablet, PC).
- **🔔 Suchabo (Sammel-Alarm):** Jede gespeicherte Suche lässt sich **beobachten** — ist
  eine Suche im Dropdown gewählt, erscheint die Abo-Zeile: **„Beobachten"** anhaken,
  **Schwellenpreis** (pro Person) setzen, **Übernehmen**. TUIWatch führt die Suche dann
  regelmäßig aus (im Takt von `poll_interval`, mindestens stündlich) und **meldet per
  Telegram/HA**, wenn ein Hotel **neu unter die Schwelle** fällt oder ein bereits
  gemeldetes **noch günstiger** wird (kein Spam: je Hotel wird der tiefste gemeldete
  Preis gemerkt; steigt es über die Schwelle und fällt später wieder darunter, kommt
  erneut eine Meldung). **„Jetzt prüfen"** führt das Abo sofort aus; die aktuellen
  Treffer unter der Schwelle lassen sich jederzeit über den Link in der Abo-Zeile als
  normale Trefferliste **anzeigen** (inkl. „Tracken"). Aktive Abos sind im Dropdown mit
  🔔 markiert.

**2. Aus einem Angebot:** Bei jedem aktiven Angebot der Button **Region** sucht **weitere
Hotels derselben Region** für dieselben Reisedaten/Dauer/Reisende/Abflughafen; Veranstalter
und Verpflegung werden aus dem Angebot vorbelegt.

**3. TUI-URL einfügen:** Unter „Alternativ: TUI-Such-URL einfügen" eine Ergebnis-URL von
tui.com (mit `regionGiataIds=…`) einfügen.

Zeigt TUI für ein Hotel gerade einen **Aktionscode/Coupon** an, erscheint „% Aktionscode
möglich" unter den Angebotsdetails (kein fester Wert — der hängt vom Reisepreis ab,
siehe tui.com für den genauen Betrag). Zutreffende **Lage-Attribute** (Direkt am
Strand, Strand < 500m, Sandstrand, Ruhig, Außerhalb) erscheinen ebenfalls als Pillen
je Treffer — „Meerseite" lässt sich nicht anzeigen, nur beim Filtern verwenden (siehe
Lage-Filter oben).

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

## KI-Fazit, -Vergleich & -Verlauf

> ⚠️ Die Anthropic-/Gemini-API ist **kostenpflichtig** (eigener API-Key,
> eigenes Konto beim jeweiligen Anbieter). Bei jedem KI-Aufruf (Fazit,
> Vergleich, TripPilot, Auto-Tag, Frag dein Portfolio) entstehen reale
> Kosten nach der Preisliste des gewählten Anbieters. TUIWatch zeigt
> geschätzte Kosten pro Aufruf sowie eine laufende Gesamtsumme seit
> Add-on-Start an — das ist eine Schätzung auf Basis der Token-Zahlen,
> **kein echtes Guthaben** und keine Abbuchung durch TUIWatch selbst; das
> tatsächliche Guthaben/die Abrechnung zeigt nur die jeweilige
> Anbieter-Console.

Mit hinterlegtem API-Key (`anthropic_api_key` bzw. `gemini_api_key`, je
nach `ai_provider`) erscheinen zusätzliche **🤖**-Buttons in der Hotelsuche
und der Angebotsübersicht (ohne Key sind sie komplett ausgeblendet).

### KI-Anbieter

`ai_provider` schaltet **global für alle KI-Features** zwischen Anthropic
(Standard) und Google Gemini um:
- **Anthropic/Claude:** `anthropic_model` (Standard `claude-opus-4-8`; auch
  `claude-sonnet-5`, `claude-haiku-4-5`, `claude-fable-5` wählbar —
  schneller/günstiger bzw. teurer). Websuche über Anthropics
  `web_search`-Tool, per `ai_max_web_searches` (Standard 12, 1-50)
  gedeckelt — niedriger spart Input-Tokens/Kosten, höher liefert
  gründlichere Antworten bei mehreren Zielen/Hotels.
- **Gemini:** `gemini_model` (Standard `gemini-3.1-pro`; auch
  `gemini-3.5-flash`, `gemini-2.5-flash` wählbar). Websuche über
  Google-Search-Grounding — **kein** Äquivalent zu `ai_max_web_searches`,
  Gemini entscheidet selbst, wie oft es sucht.

Sind **beide** API-Keys hinterlegt, erscheint im Footer ein Umschalter
(„🤖 Claude aktiv" / „✨ Gemini aktiv") — ein Klick wechselt sofort den
Anbieter für alle KI-Features, ohne die Add-on-Konfiguration zu öffnen. Ist
nur ein Key gesetzt, läuft automatisch alles über diesen (der Umschalter
bleibt dann versteckt, `ai_provider` wird ignoriert).

- **🤖 KI-Fazit** (je Suchtreffer) — Claude durchsucht live das Web (HolidayCheck,
  Tripadvisor, Google, Klimatabellen) und liefert eine ausführliche Einschätzung zu
  **Lage & Strand, Zimmer, Restaurants & Bars, Pool/Wellness, Ausstattung,
  Klima zur Reisezeit** (historische Wassertemperatur/Wetter/Wind für Ort und
  Reisemonat — keine Tagesvorhersage, sondern der langjährige Durchschnitt) sowie
  ein **Preis-Leistung-Fazit**.
- **🤖 Vergleichen** — Checkbox je Suchtreffer (max. 5), schwebende Leiste ruft
  Claude **einmal** für alle ausgewählten Hotels auf: Vergleichstabelle +
  Empfehlung, welches Hotel für wen (Familie, Paar, Party, Ruhe …) am besten passt.
  Genau dieselbe Funktion gibt es auch in der **Angebotsübersicht** über die
  bestehende Mehrfachauswahl (Sammelaktionsleiste → „🤖 Vergleichen").
- **Token- & Kosten-Anzeige** — jede Antwort zeigt Input-/Output-Tokens und die
  geschätzte Kostenschätzung in USD (Anthropic-Listenpreis) für genau diesen
  Aufruf, plus eine laufende Gesamtsumme seit Add-on-Start. **Kein echtes
  Guthaben** — das zeigt nur die Anthropic-Console; hierfür wäre ein separater
  Admin-API-Key nötig.
- **📄 PDF exportieren** — öffnet eine druckoptimierte Ansicht in neuem Tab, aus
  der sich der Browser-Druckdialog direkt als PDF speichern lässt.
- **🤖 KI-Verlauf** (Button oben neben „Alle prüfen") — alle bisherigen Fazits/
  Vergleiche bleiben **dauerhaft** gespeichert (unabhängig vom 24h-Cache, bis zu
  300 Einträge), anklickbar zum erneuten Anzeigen, einzeln löschbar.
- Ergebnisse werden **24 Stunden** je Hotel/Vergleichs-Kombination
  zwischengespeichert — erneutes Öffnen kostet keinen neuen API-Aufruf.

## 🗺️ TripPilot

Geführter Klick-Fragebogen (kein Freitext-Chat) über den **„🗺️ TripPilot"**-
Button in der Toolbar: rund 20 Schritte zu Zielregion (Mehrfachauswahl, z. B.
Balearen + Griechische Inseln gleichzeitig — „Tagesausflug in der Nähe"
schließt sich dabei mit echten Zielregionen aus), ausgeschlossenen Ländern
(nur relevant bei „Weltweit"/„Egal"), Interessen, Reiseart, Mitreisenden,
Budget, Reisedauer, Reisezeit, Wetterwünschen (Temperatur/Meer-oder-See/
Regen), Aktivitäten, Unterkunft, Hotelwünschen, Flug, was im Urlaub nervt
sowie zwei Freitext-Feldern (perfekter Urlaub, frühere Urlaubserfahrungen).
Am Ende ruft Claude einmal die passenden Ziele ab.

- **Ergebnis:** 3 konkrete Zielvorschläge (🏆/🥈/🥉) mit Begründung, plus ein
  „🔀 Alternative"-Vorschlag (bewusst leicht abweichend) und ein
  „🎲 Überraschung"-Vorschlag (Ziel außerhalb der gewählten Zielregion, an das
  man normalerweise nicht denkt).
- **Konkrete Unterkünfte je Hauptvorschlag:** in drei Kategorien (Budget/
  Mittelklasse/Gehoben) je 2-3 Nennungen, passend zur gewählten
  Unterkunftsart — bei Hotel/Apartment/Villa echte Namen, bei Ferienwohnung/
  Airbnb/Camping/Hostel konkrete Wohngegenden statt Markennamen. Nur
  überwiegend gut bewertete Unterkünfte (Websuche prüft HolidayCheck/
  Tripadvisor/Google). Verfügbarkeit/Buchbarkeit (bei TUI: auch im
  TUI-Katalog) muss der Nutzer selbst live prüfen.
- **Sicherheit eingebaut, nicht abschaltbar:** ausgeschlossene Länder werden
  nie vorgeschlagen; Claude prüft für jedes Land per Websuche aktuelle
  Reisewarnungen des Auswärtigen Amts; bei „Pauschalreise (TUI)" werden nur
  Ziele vorgeschlagen, die TUI nachweislich im Programm hat.
- **Klima/Wind ortsgenau:** Recherche möglichst auf Insel-/Teilregionsebene
  statt nur fürs Land (Wind kann z. B. auf den Kapverden zwischen Sal und
  Boa Vista stark variieren) — gilt auch für KI-Fazit und Hotelvergleich.
- **Eigene Anreise statt Flug:** bei Auto/Bus/Bahn werden Flugzeit/
  Abflughafen übersprungen, stattdessen Startort (PLZ/Ort) und maximale
  Entfernung abgefragt — Claude schlägt dann nur noch Ziele in Fahrdistanz
  vor (auch beim Alternative- und Überraschungs-Vorschlag).
- **Tagesausflug-Modus:** bei der ersten Frage „Tagesausflug in der Nähe"
  wählbar — blendet Länder, Reiseart, Mitreisende, Budget, Unterkunft,
  Flug/Anreiseart und die Freitext-Felder aus (nicht relevant ohne
  Übernachtung), fragt stattdessen Startort/max. Entfernung und verfügbare
  Zeit (Vormittag/Nachmittag/Ganzer Tag/inkl. Abend) ab. Ergebnis: 3
  Tagesausflugsziele mit Aktivität, Anfahrt, groben Öffnungszeiten/Eintritt
  und Einkehr-Tipp, keine Übernachtungsempfehlung, keine Reise-DNA-Erfassung.
- **Reise-DNA:** Nach jeder Anfrage berechnet TUIWatch zusätzlich ein
  Präferenzprofil (🌴 Strand, 🏛️ Kultur, 🎉 Nachtleben, ⛰️ Aktiv,
  🍹 Entspannung, 🍽️ Kulinarik, 👨‍👩‍👧 Familie, 💰 Preisbewusst) — rein
  deterministisch aus den Fragebogen-Antworten, **kein zusätzlicher
  KI-Aufruf/keine Zusatzkosten**. Landet als Tabelle im Ergebnis, wird über
  mehrere Anfragen als gleitender Mittelwert gespeichert und der KI beim
  nächsten Mal als Zusatzkontext mitgegeben.
- Landet wie Fazit/Vergleich im **KI-Verlauf** (inkl. gewähltem Monat im
  Titel) und ist per E-Mail versendbar.

## Eigene KI-Prompts

Über **⚙ KI-Prompts** im Footer lässt sich der Standard-Instruktionstext für
**TripPilot**, **Hotelvergleich**, **KI-Fazit** und **Tagesausflug**
einsehen und über die Checkbox „Eigenen Prompt verwenden" durch einen
eigenen Text ersetzen (max. 4000 Zeichen, „Zurücksetzen auf Standard"
jederzeit möglich).

- Bei TripPilot bleiben sicherheitskritische Klauseln (Länder-Ausschluss,
  Reisewarnungs-Check, TUI-Verfügbarkeit, Reise-DNA-Kontext) immer fix
  erhalten — nur der Recherche-/Format-/Ton-Teil des Prompts ist editierbar.
- Ergebnisse werden je nach aktivem Prompt-Text separat zwischengespeichert —
  ein geänderter Prompt liefert sofort ein neues Ergebnis statt eines
  veralteten 24h-Cache-Treffers.

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
  gespeicherten PDF und aller weiteren Anhänge.
- **Weitere Anhänge:** In der Detailansicht lässt sich über **„＋ PDF"** ein zusätzliches
  PDF hinterlegen (z. B. der Reiseplan) — **reine Ablage**, es findet keine Auswertung
  statt. Anhänge erscheinen als Pille (📎 Dateiname), Klick öffnet/lädt herunter, das
  **×** entfernt den Anhang wieder. Werden im Backup/Restore mitgesichert.
- **🔍 Debug-Modus:** In der Detailansicht zeigt **„Debug"** den **bereinigten PDF-Text**
  (die Basis der Feld-Erkennung), je Feld **erkannt/leer** und das geparste JSON — so
  sieht man bei einer TUI-Layout-Änderung sofort, *warum* ein Feld leer blieb. Schlägt
  ein Import komplett fehl, öffnet sich die Debug-Ansicht automatisch (ohne die PDF zu
  speichern). Tipp: den bereinigten Text anonymisiert als Testfall unter
  `tests/fixtures/trips/` ablegen.

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

**Trend über Zeit:** Jeder Abruf überschreibt zwar weiterhin den angezeigten Snapshot,
zusätzlich wird aber mitgeschrieben, für welche Reisedaten sich der Preis seit dem
letzten Abruf geändert hat (delta-codiert, nur echte Änderungen — kein Datenmüll bei
unveränderten Tagen). Darauf aufbauend:
- Umschalter **„📈 Trend“ / „💰 Preis“** im Kalender: die Trend-Ansicht färbt Tage nach
  Preisänderung statt nach absolutem Preis (rot = gestiegen, grün = gefallen).
- Ein Klick auf das **📈-Symbol** einer Zelle zeigt den Preisverlauf genau dieses
  Reisedatums über alle bisherigen Abrufe als Mini-Diagramm.
- **„Größte Bewegungen seit letztem Abruf“** listet die Tage mit den stärksten
  Preissprüngen auf einen Blick auf.

Diese Trend-Historie zählt zu den echten, nicht rekonstruierbaren Nutzdaten (wie der
Preisverlauf) und wird beim Zurücksetzen/Löschen eines Angebots mitgelöscht sowie im
Backup/Restore mitgesichert — anders als der reine Kalender-Snapshot (`calendar_cache`),
der weiterhin nicht gesichert wird, da er sich jederzeit neu abrufen lässt.

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

Zusätzlich `binary_sensor.tuiwatch_aktionscodes`: **an**, solange aktuell
öffentliche TUI-Aktionscodes verfügbar sind (siehe oben), sonst **aus**. Attribute:
`count`, `coupons` (Liste je `code`/`value`/`kind`), `booking_until`, `travel_period`.

Sowie `binary_sensor.tuiwatch_api_available`: **an**, solange beim letzten
API-Selbsttest alle kritischen TUI-Endpunkte erreichbar waren, sonst **aus**.
Attribute: `failing` (Liste ausgefallener Endpunkte), `checked_at`.

Und `binary_sensor.tuiwatch_cooldown_active`: **an**, solange der globale
„Jetzt prüfen"-Cooldown (60s nach `/api/check-now`) noch läuft, sonst **aus**.
Attribut: `retry_after` (verbleibende Sekunden).

Alle drei Binär-Sensoren werden per Timer alle paar Sekunden/Minuten aus dem
zuletzt bekannten Stand erneut an HA gemeldet — sie sind daher direkt nach
einem HA-Neustart wieder verfügbar, ohne auf den nächsten Live-Check zu warten.

Außerdem `sensor.tuiwatch_markttrend`: **Wert** = kumulierte Preisänderung (%) über
alle geprüften Angebote der letzten 14 Tage, oder `unavailable` bei zu wenigen
Datenpunkten. Attribute: `direction` (up/down/flat), `days` (seit wie vielen Tagen die
Richtung anhält), `samples` (Anzahl Datenpunkte), `index`/`index_pct`/`index_since`
(Index seit Aufzeichnungsbeginn, siehe unten), `by_region` (gleiche Aufschlüsselung je
Destination, nur für Regionen mit genug Daten). Siehe unten „Markttrend".

## Markttrend

Zusätzlich zum Preistrend je Angebot (auf jeder Karte, aus dessen eigener Historie)
gibt es einen **marktweiten** Trend über **alle** geprüften Angebote — unabhängig
davon, ob ein einzelnes Angebot später gelöscht wird.

- **Anzeige:** Button **📈 Markttrend** in der Werkzeugleiste öffnet ein Fenster mit
  dem Gesamttrend sowie einer Aufschlüsselung je Reisedestination (Region). Der
  Button färbt sich passend zur Gesamtrichtung ein (rot = steigend, grün = fallend),
  ohne dass das Fenster geöffnet werden muss.
- **Berechnung:** bei jedem erfolgreichen Preis-Check wird die prozentuale Änderung
  zum vorherigen Preis **dieses** Angebots festgehalten (nicht der absolute Preis —
  das macht unterschiedlich teure Hotels vergleichbar). Der angezeigte Trend ist die
  **kumulierte** Bewegung dieser Prozentwerte über die letzten 14 Tage (Zinseszins-
  Verkettung, nicht der einfache Mittelwert — sonst würden die vielen „unverändert"-
  Checks zwischen zwei Preisschritten einen echten, aber seltenen Trend im Schnitt
  fast auf null verwässern). Ab welcher kumulierten Bewegung „steigend"/„fallend"
  statt „stabil" angezeigt wird, ist über die Option `market_trend_threshold` (%,
  Standard 1.0) einstellbar. Bei weniger als 6 Datenpunkten im Fenster erscheint
  „keine Daten" (kein Hellsehen bei dünner Datenlage).
- **Index seit Beginn:** zusätzlich zum rollierenden 14-Tage-Trend zeigt „Markttrend"
  je Destination auch einen **Index (Basis 100) seit Aufzeichnungsbeginn** — ohne
  Zeitfenster, damit eine langsame Bewegung (z. B. mehrere Preisschritte über Wochen
  verteilt, dazwischen ruhige Phasen) nicht aus dem 14-Tage-Fenster herausfällt und
  unsichtbar bleibt.
- **Zimmerwechsel:** wählt man für ein Angebot ein anderes Zimmer, kann sich der Preis
  allein dadurch sprunghaft ändern — das ist keine Marktbewegung. Dieser eine
  Preisschritt fließt daher **nicht** in den Markttrend ein; die Zählung setzt direkt
  danach wieder neu an. Für bereits gesammelte Daten (z. B. ein Zimmerwechsel, der vor
  dieser Korrektur mitgezählt wurde) hilft **🔄 Neu berechnen** im Markttrend-Fenster:
  baut `price_moves` komplett neu aus der vorhandenen Preishistorie auf, ohne Daten zu
  verlieren.
- **Persistenz:** die Datenpunkte liegen in einer eigenen Tabelle, unabhängig vom
  jeweiligen Angebot — das Löschen eines Angebots hat **keinen** Einfluss auf den
  Markttrend. Beim ersten Start nach diesem Update wird die vorhandene Preishistorie
  einmalig rückwirkend eingerechnet.
- **Näherung:** die „Monate vor Abreise" je Datenpunkt wird aus Rückreisedatum minus
  angefragter Reisedauer geschätzt (kein exaktes Abreisedatum gespeichert) und fließt
  aktuell nicht in die UI-Anzeige ein, ist aber intern je Datenpunkt vorhanden.

## KI-Buchungsscore ("Orakel")

Auf Anfrage (Button-Klick, **keine** automatische Ausführung — kostet KI-Aufrufe
inkl. Websuche) schätzt die KI ein, ob gerade ein guter Zeitpunkt zum Buchen ist.
Zwei Varianten:

- **Pro Angebot** — Button **🔮 Buchungsscore** in der Angebots-Fußzeile. Nutzt den
  eigenen Preisverlauf des Angebots, dessen Trend, den Markttrend/-index seiner
  Destination sowie die Saisonalität aus dessen Preiskalender (günstigster/teuerster
  Monat, günstigster Einzeltermin). Fehlt der Preiskalender noch oder ist älter als
  7 Tage, wird er **einmalig automatisch aufgefrischt**, bevor der Score berechnet
  wird (macht diesen einen Aufruf spürbar langsamer) — ist er noch frisch, wird er
  unverändert weiterverwendet, kein unnötiger erneuter Abruf.
- **Pro Destination** — Button **🔮** je Zeile im Markttrend-Fenster. Schätzt die
  Destination allgemein ein (kein bestimmtes Hotel), nur aus deren Markttrend/-index;
  setzt mindestens so viele Datenpunkte voraus wie der Markttrend selbst.

Ergebnis: Score (0–100), Empfehlung (Jetzt buchen/Beobachten/Warten), „Vertrauen"
(%), Erwartung für 7/30 Tage sowie eine Begründung mit Punkten, die jeweils als
**[Daten]** (aus den oben genannten echten Zahlen) oder **[Annahme]** (allgemeines
KI-Wissen zu Saison/Frühbucher-Fristen oder ein Websuche-Fund) gekennzeichnet sind —
damit nicht der Eindruck einer Präzision entsteht, die die zugrunde liegenden Daten
nicht hergeben. Ergebnisse werden 6 Stunden gecacht (je Angebot bzw. Destination) und
landen dauerhaft im **KI-Verlauf**.

## Bedienung

- **Tags** — frei vergebbare Schlagworte je Angebot (＋-Pille auf der Karte); Klick auf
  einen Tag entfernt ihn wieder. Unter der Suchleiste zeigt eine Pill-Zeile alle
  aktuell verwendeten Tags — Klick filtert die Liste sofort (wie die Suche, live, kein
  Neuladen); erneuter Klick hebt den Filter auf. Wird im Backup/Restore mitgesichert.
- **Offline-Banner** — bei Verbindungsabbruch (WLAN weg, Server nicht erreichbar) erscheint
  ein abdunkelndes Overlay mit „Neu laden"-Button; verschwindet automatisch, sobald die
  Verbindung wieder da ist.
- **Als E-Mail senden** — verschickt alle (oder markierte) Angebote als HTML-Mail;
  benötigt SMTP-Optionen. Der Empfänger-Dialog bietet optional ein **Nextcloud-
  Adressbuch** (CardDAV) als Autocomplete an — dazu `nc_addressbook_url` (die volle
  Adressbuch-URL, wie sie Nextcloud in der Kontakte-App zum Kopieren anbietet),
  `nc_user` und `nc_app_password` in den Add-on-Optionen eintragen. Freitext bleibt
  ohne Adressbuch weiterhin möglich; ohne Konfiguration ändert sich nichts.
- **Backup / Wiederherstellen** — **komplettes** Backup als **ZIP**: alle getrackten
  Angebote **inkl. Preisverlauf** und Diagramm-Markern, **„Meine Reisen" inkl. der
  Original-PDFs**, die **gespeicherten Suchen**, der **dauerhafte KI-Verlauf** (Fazits/
  Vergleiche/TripPilot-Ergebnisse), die **KI-Einstellungen** (Reise-DNA,
  kumulierte Kosten-Zähler heute/Monat/gesamt, eigene KI-Prompt-Vorlagen) sowie die
  **Markttrend-Datenpunkte** (überleben so einen Umzug auf ein anderes Add-on, auch
  wenn die ursprünglichen Angebote dort nicht mehr existieren). Die
  Wiederherstellung liest die ZIP (das alte reine JSON wird weiterhin akzeptiert) und
  arbeitet **nicht-destruktiv**: Fehlendes wird ergänzt, Bestehendes bleibt erhalten
  (Abgleich per URL, Buchungsnummer bzw. Name; KI-Einstellungen/Kosten-Zähler werden nur
  gesetzt, wenn lokal noch nichts hinterlegt ist — laufende Zähler werden nie durch
  ältere Backup-Werte zurückgesetzt) — nichts wird gelöscht oder doppelt angelegt. (Reine
  Caches wie Vergleich/Kalender-Snapshot werden nicht gesichert, sie entstehen automatisch
  neu — die Kalender-**Trend-Historie** je Angebot dagegen schon, siehe Abschnitt
  „Preiskalender".)
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
- **🤖 KI-Verlauf** (nur mit hinterlegtem `anthropic_api_key`) — bisherige
  KI-Fazits/-Vergleiche einsehen, siehe [KI-Fazit, -Vergleich & -Verlauf](#ki-fazit--vergleich--verlauf).
- **Verlauf** — Diagramm + Tabelle der gesamten Preishistorie, inkl. **CSV-Export**.
- **Nächte** — Preise für kürzere/längere Reisedauern (Basis ±N) live vergleichen.
- **Zimmer** — die wählbaren **Zimmerkategorien** des Hotels mit Preis pro Person und
  Aufpreis zum günstigsten anzeigen. Standardmäßig wird das **günstigste** Zimmer
  verfolgt; per **„tracken"** lässt sich eine bestimmte Kategorie fixieren („für ein paar
  Euro mehr was Besseres"), ab dann wird deren Preis verfolgt. **„Details ↗"** öffnet das
  Zimmer mit Fotos/Beschreibung auf tui.com; **„Günstigstes automatisch"** hebt die
  Festlegung wieder auf.
- **Pausieren / Fortsetzen** — setzt die automatische Prüfung für ein Angebot aus, ohne es zu löschen.
- **Zurücksetzen** — löscht den Preisverlauf (und Vergleichs-/Kalender-Cache samt Kalender-Trend-Historie) und beginnt nach einer frischen Abfrage wieder bei „null". Angebot, Name und Wunschpreis bleiben.
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
Neustarts erhalten — Größe der Datei steht im **Footer** (aktualisiert alle
5 Minuten). Enthält u. a. auch den dauerhaften **KI-Verlauf** (Tabelle
`ai_analyses`); der 24h-Cache für Wiederholungsaufrufe liegt dagegen nur im
Arbeitsspeicher und geht bei einem Neustart verloren.

**Automatisches Backup:** Ist `auto_backup` aktiv (Standard), legt TUIWatch einmal
pro Woche ein vollständiges Backup-ZIP (Angebote inkl. Preisverlauf und Marker,
Reisen inkl. PDF, gespeicherte Suchen) unter `/addon_config/backups/` ab — im
Dateisystem von Home Assistant unter `addon_configs/<slug>_tuiwatch/backups/`.
Es werden die letzten `auto_backup_keep` (Standard 5) Dateien behalten. Anders als
`/data` bleibt dieser Ordner auch bei einer **Neuinstallation** des Add-ons bestehen;
Wiederherstellen wie gehabt über „⬆ Wiederherstellen" im Web-UI.

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
