# STR-Flugplan — Scraping-Notizen

Pendant zu [SCRAPING.md](SCRAPING.md) und [SCRAPING_CHECK24.md](SCRAPING_CHECK24.md),
aber für den optionalen Flugplan ab Stuttgart Airport (`enable_str_flights`).

## Herkunft

Quelle ist die Flugziele-Übersicht auf `stuttgart-airport.com/de/reisende-besucher/
reiseangebote/flugziele`. Diese Website selbst ist **nicht** direkt nutzbar: sie
sitzt hinter Akamai und blockt Cloud-/Rechenzentrums-IPs pauschal per Edge-Rule
(`errors.edgesuite.net`, HTTP 403 „Access Denied") — betrifft sowohl einfache
`requests`/curl-Calls als auch echten Headless-Chromium (Playwright), beide
identisch geblockt, noch bevor die Seite überhaupt rendert. Kein JS-Challenge,
kein Cookie-Bootstrap hilft — reiner IP-Block auf Edge-Ebene, kein
Bot-Detection-Problem der Seite selbst. Von einer normalen Heim-IP aus (nicht
Cloud) ist die Seite dagegen problemlos erreichbar.

Die Flugziel-Liste ist auf der Seite **nicht** serverseitig gerendert, sondern
wird per JavaScript aus einem separaten Backend nachgeladen — per
Netzwerk-Mitschnitt eines echten Seitenaufrufs (Browser-DevTools, Network-Tab,
Filter/Zielflughafen umgestellt, um den Request zu isolieren) gefunden.

## `GetConnections` — Flugplan-API

```
GET https://fsg-datahub.azure-api.net/legacy/Flightplan/GetConnections
    ?pagesize=9999&page=1
    &from=nullT00:00:00.000Z&till=nullT23:59:00.000Z
    &type=Departure|Arrival
    &category=&airline=
    &airport=<IATA-Code, z. B. LPA>&country=<Ländername, GROSSBUCHSTABEN, z. B. SPANIEN UND KANARISCHE INSELN>
```

- **Kein Auth-Header nötig** — kein `Ocp-Apim-Subscription-Key`, kein
  `Authorization: Bearer`, trotz Azure-API-Management-Backend (Hostname
  `*.azure-api.net`). Live verifiziert: ein nackter `curl`-Call ganz ohne
  User-Agent/Referer liefert `200 OK` mit vollem JSON.
- **Kein CORS-Preflight** im Browser beobachtet, kein Referer serverseitig
  geprüft (Browser sendet ihn automatisch mit, das ist Standardverhalten,
  keine App-Logik) — reiner `requests.get()` reproduzierbar, kein Playwright
  nötig (anders als ursprünglich für die Haupt-Website vermutet).
- `airport`/`country` sind reine Filter-Query-Parameter — leer gelassen
  (`airport=&country=`) liefert die **komplette** Flugplan-Tabelle
  (`TotalItems: 2060` für `type=Departure`, live gemessen). `pagesize=9999`
  reicht, um alles in einer Seite zu bekommen (`TotalPages: 1`).
- `type=Arrival` liefert dieselbe Struktur für ankommende statt abgehende
  Flüge (z. B. 22 Einträge für `airport=LPA`).
- Response-Header: `Content-Type: application/json; charset=utf-8`,
  `Cache-Control: max-age=60`, `Server: Microsoft-IIS/10.0`.

Antwortform (gekürzt):

```json
{
  "CurrentPage": 1, "TotalPages": 1, "TotalItems": 21, "ItemsPerPage": 9999,
  "Items": [
    {
      "Type": "Departure", "Category": "Default",
      "Airline": {"Code": "EW", "Name": "EUROWINGS"},
      "FlightName": "2262",
      "Airport": {"Code": "LPA", "Name": "GRAN CANARIA",
                  "Country": "SPANIEN UND KANARISCHE INSELN",
                  "Latitude": null, "Longitude": null, "Altitude": null},
      "Weekdays": {"Monday": false, "Tuesday": false, "Wednesday": false,
                   "Thursday": false, "Friday": false, "Saturday": true, "Sunday": false},
      "Departure": "06:10", "Arrival": "09:45", "Via": null,
      "DateFrom": "2026-10-31T00:00:00", "DateTill": "2027-03-27T00:00:00"
    }
  ]
}
```

Ein `Items`-Eintrag = **eine Zeile im Saisonfahrplan**, nicht eine einzelne
Flugbewegung: `Weekdays` gibt an, an welchen Wochentagen der Flug im Zeitraum
`DateFrom`–`DateTill` verkehrt. Derselbe Zielflughafen taucht deshalb oft
mehrfach auf (unterschiedliche Wochentage/Saisonabschnitte je eigener Zeile).
`Via` ist bei Direktflügen `null`; bei Flügen mit Zwischenstopp vermutlich der
Wochentag-Flughafencode (nicht live beobachtet, da im Testsample keine
Verbindung mit `Via` vorkam).

## Client-Implementierung (`str_flights_client.py`)

- Holt beim ersten Aufruf **einmal** die komplette Liste (`Departure` +
  `Arrival`, ungefiltert) und hält sie 6 h im Prozess-Speicher (`_CACHE_TTL`).
  Alle Suchen (`search_connections()`) filtern danach rein clientseitig
  (Python) über den Cache — kein wiederholter Request ans Flughafen-Backend
  pro Tastenanschlag in der UI.
- Bei Fehlschlag beim Nachladen wird der letzte gültige Cache-Stand weiter
  ausgeliefert statt eines leeren Ergebnisses (Fail-Soft, analog anderen
  Cache-Stellen im Add-on).
- Suche matched Zielflughafen-Code, -Name **und** Land als ein
  Substring-Feld (z. B. „Spanien" findet auch „GRAN CANARIA" über das
  `Country`-Feld) — kein separates Autocomplete-API wie bei Check24 nötig,
  da die komplette Liste bereits lokal vorliegt.

## Risiko-Hinweis

Offener, unauthentifizierter Endpoint eines Drittanbieters (Flughafen
Stuttgart GmbH, nicht offiziell als öffentliches API dokumentiert) —
Wartungsrisiko bei Layout-/Backend-Änderungen wie bei TUI/Check24, aber kein
Anti-Bot-Umgehungsrisiko (kein Playwright, kein Browser-Fingerprinting nötig).
`enable_str_flights` bleibt trotzdem Opt-in (Default aus). Reine
Flugplan-Daten (Linienflüge), **keine** Pauschalreise-Preise — unabhängig von
TUI/Check24-Angeboten, keine Verknüpfung zu einzelnen Reisen.
