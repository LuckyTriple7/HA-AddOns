# Check24-Vergleich — Scraping-Notizen

Pendant zu [SCRAPING.md](SCRAPING.md), aber für den optionalen Check24-Preisvergleich
(`enable_check24_compare`).

## Korrektur (v0.55.5): doch ein offenes JSON-API

Bis v0.55.4 wurde angenommen, Check24 habe **kein** brauchbares JSON-API und die
Angebotsseite müsse per Playwright gerendert werden, weil die Antwort von
`/suche/json/dynamic/offer` ein Feld `cryptString` enthält. Diese Annahme war
**falsch** — per Netzwerk-Mitschnitt eines echten Seitenaufrufs (Playwright mit
Response-Interception, alle Requests/Responses geloggt statt nur die vermuteten)
zeigt sich:

- `cryptString` ist nur ein **Buchungs-/Verfügbarkeits-Token** (`data-vacancy` im
  DOM), das beim eigentlichen Buchen an `POST /suche/json/dynamic/store-vacancy`
  zurückgeschickt wird, um die Verfügbarkeit final zu bestätigen. Es hat mit der
  Anzeige von Preis/Zimmer/Verpflegung nichts zu tun.
- Dieselbe Antwort von `/suche/json/dynamic/offer` enthält **im Klartext** alles,
  was vorher mühsam aus dem gerenderten Seitentext geregext wurde:
  `price.effectivePrice.amount` (Preis pro Person), `accommodationData.mealType`
  (Verpflegung, z. B. `"AllInclusive"`), `accommodationData.roomDescription.
  {name,description}` (Zimmer), `accommodationData.transfer`, `tourOperatorCode`
  + `tourOperatorAlias` (Veranstalter, Klartext-Name), `travelAttributes`
  (Reisedaten), `detailsUrl` (Deep-Link zum Angebot).
- Der Endpoint ist ein simpler **Job/Poll-POST** (Formular-encoded, kein JS-
  Krypto nötig), mit reinem `requests` reproduzierbar — kein Browser nötig.
- Die Hotelsuche (`search_hotel`) ist ebenfalls ein normales JSON-**GET**
  (`/autocompleter-destination?term=...`), kein rein clientseitiges Autocomplete
  wie zuvor angenommen.

`check24_client.py` nutzt daher **kein Playwright mehr** — nur noch `requests`.
Playwright bleibt im Add-on installiert, weil `scraper.py` es für den TUI-
Browser-Fallback weiterhin braucht.

## `/suche/json/dynamic/offer` — Angebots-API

```
POST https://urlaub.check24.de/suche/json/dynamic/offer
Content-Type: application/x-www-form-urlencoded
Referer: <die exakte /suche/angebot?...-URL, siehe unten>
X-Requested-With: XMLHttpRequest

transactionId=<uuid4>&clientId=<uuid4>&previousSearchUrl=&disableCache=1
&forceFailedVacancies=0&forceEstaHint=0&forceErrorVacancies=0
&forceFlightTimeChange=0&forceCancellationNotAvailable=0
&searchUrl=<urlencoded /suche/angebot?...-URL>&withTravelExperts=1
&isWithServiceInformation=0&isWithPriceAlarm=1
```

`searchUrl` ist die eigentliche Anfrage — dieselben Query-Params wie die
Angebotsseite selbst (`hotelId`, `departureDate`, `returnDate`, `days=exact`,
`airport`, `roomAllocation`, `transportType=flight`, optional `cateringList`,
siehe unten). `transactionId`/`clientId` sind vom Aufrufer frei erzeugbare
UUIDs (nicht serverseitig vorregistriert — mit `uuid.uuid4()` in Python
reproduzierbar). **Kein vorheriges Session-/Cookie-Bootstrap nötig** — ein
kalter `requests.Session()`-POST ohne vorherigen Seitenaufruf funktioniert
(live getestet).

Antwort ist ein **Job/Poll-Zyklus über denselben Endpoint** (kein separater
Poll-Call nötig): derselbe POST liefert beim ersten Aufruf `{"status":
"Pending", "items": {...teilweise gefüllt...}}`, bei Wiederholung (alle ~1.5s)
wachsende `items` bis `{"status": "Success", "items": {...alle 25(!) Angebote
mit vollem Preis/Board/Room...}}`. Live beobachtet: 4-7 Polls, ~8-15s
Gesamtdauer. **Drei** Terminal-Status ohne weiteres Polling, nicht nur zwei:
- `"Error"` — z. B. ungültige `hotelId`.
- `"Empty"` — **gültiges** Hotel, aber 0 Angebote für exakt diese Termine,
  antwortet sofort (<1s), live verifiziert (Gloria Palace Amadores, 11829,
  03.–14.05.2027, echt ausgebuchtes Beispiel). Bis v0.57.1 fehlte dieser
  Status in der Terminal-Liste (nur `Success`/`Error` erkannt) — der Poll-Loop
  lief dann bis zum Timeout (~60s) durch, obwohl Check24 "kein Angebot" schon
  beim allerersten Call mitgeteilt hatte (Bugreport: "dauert bis zu 60s und
  dann kommt nicht mal ein Fehler").
Beide (`Error`/`Empty`) sind kein technischer Fehler, sondern Datenverfügbarkeit.

Ein `items`-Eintrag (gekürzt, echtes Beispiel hotelId=240, AI, Dez. 2026):

```json
{
  "id": "12673045011152555664", "hotelId": 240,
  "tourOperatorCode": "FER", "tourOperatorAlias": "FERIEN Touristik",
  "supplierCode": "tt", "cryptString": "0I4l...(Buchungstoken, nicht Preis)",
  "travelAttributes": {"overnightStays": 7, "departureDate": "2026-12-06T00:00:00",
                        "returnDate": "2026-12-13T00:00:00", "roomCount": 1},
  "accommodationData": {
    "mealType": "AllInclusive",
    "roomDescription": {"name": "Suite", "description": "Fam.Suite BK/TE"},
    "transfer": "Transfer"
  },
  "price": {"effectivePrice": {"amount": 1238}, "totalPrice": {"amount": 1238}},
  "detailsUrl": "/hib/240/hotel?date=2026-12-06&touroperator=FER&..."
}
```

Beobachtete `mealType`-Werte: `AllInclusive`, `AllInclusivePlus`, `FullBoard`,
`FullBoardPlus`, `HalfBoard`, `HalfBoardPlus`, `Breakfast`, `RoomOnly`/`None` —
`check24_client._MEAL_TYPE_TO_BOARD` übersetzt auf deutsche Texte (kompatibel
mit `scraper.BOARD_TYPES`, damit TUI-`board`-Werte per Substring dagegen
matchen können).

## Verpflegungs-Filter (`cateringList`)

Check24 hat auf der Angebotsseite selbst einen Verpflegungs-Filter (Tabs
„Ohne Verpflegung" / „Mind. Frühstück" / „Mind. Halbpension" / „Mind.
Vollpension" / „All Inclusive"). Ein Klick auf den Tab (`li.js-catering-tab`,
`data-min-value`) hängt `cateringList=<data-min-value>` an die URL — live per
Klick-Beobachtung ermittelt:

| Tab-Text            | `cateringList`-Wert (kommagetrennt, "diese Stufe oder besser")               |
|----------------------|------------------------------------------------------------------------------|
| Ohne Verpflegung     | `none`                                                                        |
| Mind. Frühstück      | `breakfast,halfboard,halfboardPlus,fullboard,fullboardPlus,allinclusive,allinclusivePlus` |
| Mind. Halbpension    | `halfboard,halfboardPlus,fullboard,fullboardPlus,allinclusive,allinclusivePlus` |
| Mind. Vollpension    | `fullboard,fullboardPlus,allinclusive,allinclusivePlus`                      |
| All Inclusive        | `allinclusive,allinclusivePlus`                                              |

Jede Stufe ist **"diese oder besser"**, kein exaktes Match — Check24 bietet
keinen "genau diese Stufe"-Filter an. `check24_client._build_offer_url()`
setzt `cateringList` direkt in `searchUrl` (gemappt vom TUI-Verpflegungstext
über `_catering_list_for_board()`), server-seitig gefiltert statt nur
client-seitig nachträglich validiert — verhindert, dass z. B. ein Halbpension-
Angebot als "billigere Alternative" zu einem All-Inclusive-TUI-Angebot
durchrutscht (Bugreport v0.55.4).

## Hotelsuche: `/autocompleter-destination`

```
GET https://urlaub.check24.de/autocompleter-destination?v=2_0_0&term=<query>&agent=urlaub
```

Normales JSON-GET, kein JSONP-Callback nötig (der im Browser beobachtete
`callback=jQuery...`-Parameter ist optional — ohne ihn kommt direktes JSON
zurück, kein Server-Roundtrip-Unterschied). Antwortform:

```json
{"data": [
  {"group": "destination", "data": [...Städte/Regionen, hier irrelevant...]},
  {"group": "hotel", "data": [
    {"id": 11829, "label": "Gloria Palace Amadores Thalasso & Hotel",
     "regionName": "Gran Canaria", "countryName": "Spanien", "type": "hotel"},
    ...
  ]}
]}
```

`data[].group=="hotel"` enthält die Hotel-Treffer, `id` ist die `hotelId`.
Matched auch Teilstrings/Umgebung (Ort, Region), nicht nur den Hotelnamen
selbst — bei einer langen, spezifischen TUI-Hotelbezeichnung kommen daher oft
mehrere Treffer zurück. `search_hotel()` sortiert per `difflib.SequenceMatcher`
nach Ähnlichkeit zur Anfrage und reduziert auf den Top-Treffer, wenn dieser
eindeutig ist (Score ≥0.92, Abstand zum Zweitplatzierten ≥0.08) — sonst bleibt
die volle Liste zum Anklicken.

## Risiko-Hinweis

Kein verschlüsseltes/verschleiertes Payload mehr im Spiel — die JSON-API ist
offen lesbar, ähnliches Risikoprofil wie TUIs eigenes API (Wartungsrisiko bei
Layout-/API-Änderungen, kein Anti-Bot-Umgehungsrisiko wie beim vorherigen
Playwright-Ansatz). `enable_check24_compare` bleibt trotzdem Opt-in
(Default aus), da es sich um einen externen, nicht offiziell dokumentierten
Endpoint handelt.
