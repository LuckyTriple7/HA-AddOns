# FKB-Saisonflugplan — Scraping-Notizen

Pendant zu [SCRAPING_STR.md](SCRAPING_STR.md), [SCRAPING_FRA.md](SCRAPING_FRA.md) und
[SCRAPING_MUC.md](SCRAPING_MUC.md), für den optionalen Saisonflugplan ab/nach
Karlsruhe/Baden-Baden (FKB, „Baden-Airpark", `enable_fkb_flights`). Code:
[fkb_flights_client.py](fkb_flights_client.py).

## Herkunft

Die Seite `baden-airpark.de/passagiere-besucher/fluege/saisonflugplaene/` ist
WordPress und rendert die Flugtabelle **nicht** serverseitig — das HTML enthält nur
den leeren Block. Die Tabelle kommt per JavaScript aus `admin-ajax.php`; die
Aufrufform steht im Theme-Bundle `public/js/block-flight-map.*.js` (Helper `jQ`:
`fetch(url, {method:"POST", body: JSON.stringify(params)})`) und im
`data-ajax`-Attribut des Blocks (`{"ajaxUrl":…,"action":"flightmap","filters":{…}}`).

Keine IP-/Edge-Sperre wie bei Stuttgart; ein nackter `requests.post` ohne Referer,
Cookie oder Nonce liefert 200.

## Endpunkt

```
POST https://www.baden-airpark.de/wp/wp-admin/admin-ajax.php?action=flightmap
Content-Type: application/json

{"airport":"all","date":null,"season":"all","type":"departures",
 "flight":null,"plane":null,"page":1,"offset":0,"limit":-1}
```

Antwort:

```json
{"success": true, "data": {"posts": "<div role=\"row\" class=\"flight-table__row\">…", "mapRoutes": []}}
```

- **Muss POST mit JSON-Body sein.** Dieselben Werte als GET-Query-Parameter geben
  `200 OK` mit `"posts":"empty"` zurück — kein Fehler, einfach leer. Live geprüft mit
  allen naheliegenden Varianten (mit/ohne `page`, `p`, `Referer`,
  `X-Requested-With`, leere vs. `null`-Strings): alle leer.
- **`type` muss ein String sein**, nicht die Liste, die das Frontend intern führt.
  `["departures"]` liefert `success: false` mit
  `App\Flights\Enum\FlightType::tryFrom(): Argument #1 ($value) must be of type
  string|int, array given` samt Serverpfad — deshalb prüft der Client `success`,
  bevor er `data` als Objekt behandelt (im Fehlerfall ist `data` ein String).
- `limit: -1` liefert **alles** in einer Antwort (live: 534 Abflüge, 542 Ankünfte über
  alle veröffentlichten Saisons); `limit: 10` + `offset` wäre das Paging der Website.
- `airport` ist der IATA-Code (`PMI`, `AYT`, …) oder `all`; `season` ist `all` oder
  `summer-2026` / `winter-2026` / `summer-2027` / `winter-2027`; `plane` ein
  Flugzeugcode (`320`, `32N`, …); `date`/`flight` bleiben `null`.
- Die Auswahllisten (49 Ziele, 4 Saisons, 16 Flugzeugtypen) stehen als `<option>` im
  HTML der Seite. Der Client braucht sie nicht — er holt immer den vollen Plan und
  filtert lokal, wie STR/MUC.

## Antwortform

`data.posts` ist **fertig gerendertes HTML**, kein Datensatz je Flug — anders als bei
STR (JSON) und FRA (JSON). Es gibt keinen zweiten Endpunkt mit Rohdaten (gesucht:
`wp-json`, REST-Routen, `mapRoutes` — Letzteres ist nur Kartengeometrie und bei
diesen Abfragen leer). Deshalb wird geparst.

Eine Zeile (`div[role=row].flight-table__row`) hat Zellen mit sprechenden Klassen:

| Zelle | Inhalt |
|---|---|
| `flight-table__col__origin` | `Palma de Mallorca (PMI)` + Flugnummer `FR 5182` |
| `flight-table__col__type` | `06:00 - 07:55` + 7 `flight-day--<n>`-Spans (Kürzel oder `-`) |
| `flight-table__col__validity` | `01.04.2026 - 21.10.2026` + `(Sommerflugplan 2026)` |
| `flight-table__col__plane` | `Boeing 737-800`, Sitzplätze im `data-bs-title` des Info-Knopfs |
| `flight-table__col__airline` | Airline-Name, als Link auf deren Website |

Geparst wird **je Zelle über die Klasse**, nicht über die Spaltenreihenfolge: der
tagesaktuelle Flugplan derselben Website (`…/tagesaktueller-flugplan/`, anderer
`action`-Wert) benutzt dieselben Klassen in anderer Reihenfolge und mit anderen
Zellen (Gate, Status, Wartezeit Sicherheitskontrolle).

Ein Land nennt der Saisonplan nicht. `country` bleibt deshalb leer und wird in der
kombinierten Zielliste ([all_flights_routes.py](all_flights_routes.py)) aus den
anderen Flugplänen ergänzt, sofern dasselbe Ziel dort vorkommt.

## Wartung

Bricht die Tabelle, liegt es fast sicher an geänderten CSS-Klassen des Themes —
`_ROW_RE`/`_CELL_RE` in [fkb_flights_client.py](fkb_flights_client.py) sind die
einzigen Stellen, die vom Markup abhängen. Zum Nachsehen reicht:

```python
import fkb_flights_client as c
print(c.search("PMI", direction="departure", verbose=True)["total"])
```

Liefert das 0, aber der Endpunkt antwortet mit `success: true`, hat sich das Markup
geändert; kommt `posts: "empty"`, hat sich die Anfrageform geändert (beides wird
geloggt).

## Nicht genutzt: der tagesaktuelle Flugplan

`…/fluege/tagesaktueller-flugplan/` liefert dieselben Daten tagesweise
(`action=flight-results-block-departures|…-arrivals`, GET, `date=YYYY-MM-DD`,
Post-ID `p=122`) **serverseitig gerendert**, zusätzlich mit Ist-Zeit, Status, Gate und
voraussichtlicher Wartezeit an der Sicherheitskontrolle. Für die Frage „wohin komme
ich ab FKB, wann" ist der Saisonplan die bessere Quelle (ein Abruf statt einer je
Tag); der Tagesplan wäre eine mögliche Ergänzung für Live-Status am Reisetag.
