# MUC-Flugplan — Scraping-Notizen

Dritter Flugplan neben [SCRAPING_STR.md](SCRAPING_STR.md) (JSON-API,
Saisonstrecken) und [SCRAPING_FRA.md](SCRAPING_FRA.md) (JSON, Einzelflüge) —
für München, Schalter `enable_muc_flights`. Code:
[muc_flights_client.py](muc_flights_client.py).

## Warum PDF und nicht API

Die Website hat einen Flugsuche-Endpunkt (`/flightsearch/departures`,
`/flightsearch/arrivals`, Autocomplete unter
`/flightsearch/autocomplete_airport?search_term=…`), der aber **nur ein
Live-Fenster von rund ±2 Tagen** abdeckt — die Widget-Konfiguration auf
`munich-airport.de/flugplan` sagt das selbst (`min_date`/`max_date` liegen einen
Tag vor bzw. hinter heute). Live geprüft: für morgen kommen Zeilen (Condor
DE 1508, 05:55 → 08:05 nach PMI), für übermorgen kommt gar keine Tabelle mehr.
Antworten sind außerdem HTML-Fragmente, kein JSON. Für einen Flugplan taugt das
nicht.

Der **komplette Saisonflugplan** steht dagegen als PDF auf derselben Seite
(„Aktueller Flugplan", ~490 kB, 62 Seiten). Inhalt ist dasselbe Datenmodell wie
beim Stuttgarter API: Verbindung mit Wochentagsraster und Gültigkeit von–bis.

## PDF finden

```
GET https://www.munich-airport.de/flugplan          → HTML
    href="/_b/<hash>/flugplan.pdf"                  → absolute PDF-Adresse
```

- Der Pfad enthält einen **Hash** und kann sich bei jeder Neuerzeugung ändern —
  **nie hart kodieren**, immer von der Seite auflösen (`resolve_pdf_url()`).
- Der Server schickt **weder `Last-Modified` noch `ETag`**, nur
  `Cache-Control: max-age=300, s-maxage=900`. Als Änderungsmerkmal dienen daher
  **Adresse + `Content-Length`** (HEAD), im Zweifel die Felder im PDF selbst.
- Das PDF wird **täglich neu erzeugt** (PDF-Metadaten `CreationDate`, im
  Dokument die Zeile „Datenstand: TT.MM.JJJJ", auf der Seite dasselbe Datum).
  Der abgedeckte **Zeitraum** bleibt aber die laufende Saison, z. B.
  „SOMMER 2026 (ZEITRAUM SAISON: 29.03.2026 BIS 24.10.2026)". Täglich ändert
  sich also nur der Stand, nicht das Fenster.
- Deshalb: alle `CHECK_INTERVAL` (3 h) nur **prüfen** (ein GET auf die Seite,
  ein HEAD auf das PDF), und ausschließlich bei Abweichung neu laden und parsen.

## Zeilenformat

```
L/S Flug-Nr - Ziel ab MUC + Ziel an Tag Ziel Stop von bis Term. Airlinename
L  EY 125  02:35     06:55  1234567 AUH      22.08.26 24.10.26 1 Etihad Airways
S  EY 128  22:30 +   06:20  1234567 AUH      01.09.26 22.09.26 1 Etihad Airways
L  DL 130  -   17:25 08:25  1234567 ATL      13.08.26 01.09.26 1 Delta Air Lines
```

- **`S` = Start ab MUC** (Zeit 1 = ab MUC, Zeit 2 = an Ziel),
  **`L` = Landung in MUC** (Zeit 1 = ab Ziel, Zeit 2 = an MUC). Live gegen die
  Flugtafel des Flughafens gegengeprüft: `S DE 1508 05:55 08:05 … PMI` ist
  exakt der Flug, den die Tafel für den 13.08. als 05:55 ab MUC → 08:05 an PMI
  zeigt.
- **`+` vor der zweiten Zeit** = Ankunft am Folgetag, **`-` vor der ersten** =
  Abflug am Vortag (301 bzw. einige hundert Zeilen im Sommerplan).
- Wochentage als 7-Zeichen-Maske (`12-456-`), `-` = fliegt nicht.
- Zwischen Ziel-Code und Datum kann ein **zweiter IATA-Code** stehen: der
  Zwischenstopp (selten, ~8 Zeilen).
- Der **Airlinename kann fehlen** (3 Zeilen im Sommerplan) — deshalb optional.
- Terminalwerte: `1`, `2`, vereinzelt `1F`.
- Ergebnis aktuell: **3.337 Zeilen erkannt, 0 unerkannt** (Sommer 2026).

## Ziel-Überschriften (Stadt/Land)

Vor jedem Block steht eine Überschrift mit Stadt, IATA-Code und Land, verteilt
auf zwei Spalten derselben Zeile (Stadt links bei x≈54, Land rechts bei x≈360).
Die Textextraktion mischt die Reihenfolge, deshalb wird über die **x-Position
des `(CODE)`-Tokens** getrennt: alles links davon ist Stadt, alles rechts Land.

**Stolperfalle:** Das **Inhaltsverzeichnis** am Heftanfang listet dieselben Codes
in umgekehrter Spaltenfolge (Land links, Stadt rechts) — wertet man es mit aus,
wird aus „Palma de Mallorca / Spanien" ein „Spanien / (leer)". `_airport_names()`
überspringt deshalb alle Seiten ohne Flugzeilen (Deckblatt, Airline-Verzeichnis,
Inhaltsverzeichnis).

## Kosten

Download ~490 kB, Parsen mit `pdfplumber` **~15 s** für 62 Seiten. Läuft nur bei
Änderung und im Hintergrund-Thread (`_muc_flights_worker` in app.py, wärmt den
Speicher beim Start vor); Suchen laufen danach rein im Speicher.

**Risiko / Wartung:** reines PDF-Layout-Parsing, also fragiler als die beiden
JSON-Quellen. Ändert der Flughafen das Layout, greift `_ROW_RE` nicht mehr — das
Add-on protokolliert dann „PDF enthielt keine erkennbaren Flugzeilen" und behält
den letzten Stand. Zum Nachkalibrieren: PDF laden und die Zeilen mit
`pdfplumber` extrahieren, Aufbau oben vergleichen. Zweite Einschränkung ist
inhaltlich: **nur die laufende Saison** — nach dem Saisonwechsel (Ende Oktober
bzw. Ende März) steht der Folgezeitraum erst im nächsten PDF.
