# FRA-Flugplan — Scraping-Notizen

Pendant zu [SCRAPING_STR.md](SCRAPING_STR.md), aber für den optionalen Flugplan
ab/nach Frankfurt Airport (`enable_fra_flights`). Code:
[fra_flights_client.py](fra_flights_client.py).

## Herkunft

Die Fluginformations-Seite `frankfurt-airport.com/de/am-flughafen/fluege.html`
lädt ihre Tabelle per JavaScript aus zwei JSON-Endpunkten derselben Domain
(AEM-Selektoren, im HTML der Seite als absolute URLs hinterlegt und dort
gefunden — kein Netzwerk-Mitschnitt nötig). Die Subdomain
`flights.frankfurt-airport.com` (Ypsilon-Board) wird **nicht** genutzt.

Anders als bei Stuttgart gibt es hier **keine** IP-/Edge-Sperre gegen
Cloud-Adressen; ein nackter `requests.get` ohne Referer/Cookie liefert 200.

## Endpunkte

```
GET https://www.frankfurt-airport.com/de/_jcr_content.flights.json/search?q=<Text>
GET https://www.frankfurt-airport.com/de/_jcr_content.flights.json/filter
    ?flighttype=departures|arrivals
    &airport=<IATA>[,<IATA>…]
    &airline=<IATA-Airline-Code>
    &page=<n>
```

- **`search`** → `airports.data[]` mit `id` (IATA), `name`, `land`, `regionorg`,
  `icao`, `lat`/`lng`. Dient dazu, Freitext („Palma") in Codes aufzulösen
  (`SPC`, `PMI`).
- **`filter`** → `data[]` (Flüge), plus `results` (Gesamttreffer), `maxpage`,
  `page`, `entriesperpage`, `filter` (interpretierte Eingabe), `lusaison`
  (Stand der Flugplandaten).
- Ohne `flighttype` wird `departures` angenommen. Ein **ungültiger** Wert
  liefert HTML statt JSON → Antwort nie ungeprüft `json()`-parsen.
- `airport` ist **case-sensitiv**: `LPA` liefert Treffer, `lpa` liefert 0.
  Mehrere Codes kommagetrennt sind erlaubt (`airport=LPA,PMI`).
- Kein Auth-Header, kein `Ocp-Apim-…`, kein Referer-Zwang, kein Cookie.

Flug-Eintrag (gekürzt, live):

```json
{"sched":"2026-08-13T11:45:00+0200","schedArr":"2026-08-13T15:25:00+0000",
 "fnr":"DE 1404","al":"DE","alname":"Condor","iata":"LPA","apname":"Gran Canaria",
 "terminal":"1","halle":"B","gate":"B4","schalter":"656-688","ac":"A32B",
 "reg":"DAIAG","duration":280,"stops":0,"cs":["EK 3946","EY 6925"]}
```

## Stolperfallen

- **`schedArr` trägt einen falschen Offset.** Der Zeitwert ist die *Ortszeit am
  Ziel*, gestempelt wird aber `+0000`. Gegengerechnet über `duration`: Abflug
  11:45 CEST = 09:45 UTC, +280 min = 14:25 UTC = 15:25 Ortszeit Kanaren —
  genau der Wert im Feld. Deshalb nur die **Uhrzeit** (`[11:16]`) übernehmen und
  als Ortszeit am Ziel beschriften, niemals den Offset auswerten.
- **Kein Datumsfilter.** `date`, `from`, `day`, `time` werden allesamt ignoriert
  (live geprüft: identische `results`). Die Liste ist aber **chronologisch
  sortiert**, deshalb sucht `_find_start_page()` die Startseite eines Zeitraums
  per **Binärsuche** über `page` (~5 statt bis zu 22 Abrufe).
- **`entriesperpage` ist nicht steuerbar** — bleibt bei 25, egal was man
  übergibt. Ohne Zielfilter sind das 123.289 Abflüge / 4.854 Seiten; die
  Gesamtliste ist also **nicht** abholbar (anders als bei STR, wo ein Aufruf mit
  `pagesize=9999` alles liefert). Deshalb wird immer **nach Ziel gefiltert** und
  auf `_MAX_PAGES` (12 Seiten = 300 Flüge) begrenzt.
- **Datenmodell ≠ STR.** Frankfurt liefert Einzelflüge je Datum, Stuttgart
  Saisonstrecken mit Wochentagsraster. Beide Clients bleiben deshalb bewusst
  getrennt; gemeinsam ist nur der ✈️-Einstieg mit Flughafen-Auswahl im Frontend.

**Risiko / Wartung:** Der Pfad hängt an der AEM-Seitenstruktur
(`/de/_jcr_content.flights.json/…`). Zieht Fraport die Seite um, findet man den
neuen Pfad wieder, indem man das HTML der Fluginformations-Seite nach
`flights.json` durchsucht — dort stehen die URLs im Klartext.

## Zielliste (Übersichtstabelle) — separate Drittseiten-Quelle

Wie oben beschrieben liefert die offizielle API **keine** Gesamtliste. Für die
Flugziel-Übersichtstabelle (siehe all_flights_routes.py) wird deshalb eine
**andere, nicht amtliche** Quelle genutzt: `fra_board_client.py` liest das
Tagesbord von `airport-frankfurt-am-main.de` (Fußzeile „© by FraHub", **nicht**
Fraport):

```
GET https://www.airport-frankfurt-am-main.de/flugzeiten/abflug-fra.json
```

Live per HTML-Quelltext der Seite `/abflug-flughafen-frankfurt-airport`
gefunden (DataTable-Init mit `ajax.url`). Liefert nur den **heutigen** Tag
(kein Datumsparameter gefunden) — `fra_board_client.py` akkumuliert deshalb
über ein rollierendes 9-Tage-Fenster auf Platte (`TUIWATCH_DATA/
fra_board_destinations.json`), damit auch nur wöchentlich fliegende Ziele
auftauchen. Bleibt eine **Näherung**, kein amtlicher Fahrplan — Frontend
kennzeichnet FRA-Einträge in der Tabelle entsprechend (`FRA*`).

**Stolperfalle: AIRail-Bahnzubringer.** Das Board mischt Lufthansas
Bahn-Ersatzverbindungen (15 Stück im Board vom 17.08.2026) unter eigenem
IATA-artigem Code (`XHJ`, `QPP`, `ZBA`, `ZMB`, `ZWS`, `QKL`, `QFB`, …) in
dieselbe Spalte wie echte Flüge. Kein Muster im Code selbst erkennbar, aber
der Name verrät es — allerdings in **zwei** Schreibweisen: ausgeschrieben
(`"Aachen Hauptbahnhof"`, `"Basel Bad Bahnhof"`) *und* abgekürzt
(`"Dortmund Hbf"`, `"Münster HBF"`). Ein Filter nur auf `"bahnhof"` lässt die
abgekürzte Hälfte durch (so kam „Freiburg Hbf“ in die Zieltabelle); deshalb
Regex `\b(hbf|hauptbahnhof|bahnhof|bf|railway station)\b` (`_is_rail()`),
Wortgrenze gegen Fehltreffer in echten Zielnamen. Der Filter greift auch beim
Laden des persistierten Fensters, sonst blieben Altlasten bis zum Ablauf der
9 Tage stehen.

Diese Quelle wird **nur** für die Übersichtstabelle verwendet, **nicht** für
die gezielte Suche (`/api/flights/search`) — die bleibt bei der offiziellen
API oben.
