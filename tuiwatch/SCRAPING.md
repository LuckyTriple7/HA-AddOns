# TUIWatch — Scraping-Wartung

Diese Datei dokumentiert, **wie** TUIWatch den Preis von tui.com liest und **was zu
tun ist, wenn TUI das Layout ändert** (dann bricht das Auslesen und muss neu
kalibriert werden). Damit muss niemand bei null anfangen.

## Primär: offene JSON-API (seit v0.3.0)

Die Angebotsseite versorgt sich aus **offenen JSON-Endpoints** (CloudFront), die sich
**direkt per `requests.get` ohne Browser** abrufen lassen — schneller (~0,5 s statt
30–60 s) und deutlich robuster (kein HTML-Parsing). Das ist jetzt der **Standardweg**;
der Browser-Scraper ist nur noch **Fallback**. Code: `fetch_price_api()` in
[scraper.py](scraper.py).

| Zweck | Endpoint | Schlüssel-Felder |
|---|---|---|
| **Angebote + Preis** | `https://d2z3tkv1undzra.cloudfront.net/data?giataId=…&startDate=…&endDate=…&durations=…&travellers=…&airports=…&roomTypeOpCodes=…&…` | `offers[]` mit `cheapest`, `calculatedPricePerPerson`, `calculatedOriginalPricePerPerson`, `discount`, `cancellationType`, `lengthOfStay`, `rooms[]` (`description`,`code`,`boardDescription`), `departure`/`return` (Datum/Zeit/`airline`/`stopOver`/Airports), `arrivalDate`; dazu `hotel.name`, `currency`, `travellers[]` |
| **Sterne + Bewertung** | `https://d1pagbczmuq2ek.cloudfront.net/data?giataId=…&locale=de_DE` | `category` (Sterne), `holidayCheckRatings.averageRating` (×/6), `.countReviewsCurrent`, `.recommendation` (%) |
| **Ort/Region** | `https://api.cloud.tui.com/breadcrumb/v1/data/TUICOM/de-DE/3/<giataId>` | Liste Land›…›Region›Stadt›Hotel. Stadt = vorletzter Eintrag; Region = Eintrag mit `giataId == regionGiata` (sonst letzter `level==1`). Stabiler Host. |
| **Hotelbeschreibung-PDF** | `https://www.tui.com/api/hotelInfoPdf?bookingtype=2&date=TT.MM.JJJJ&bookingsequence=<hotel.product>&operator=<tourOperator>&provider=<supplier.provider>&giata=<giataId>&promotion=<programType>` | Liefert das offizielle Hotel-PDF. Alle Parameter stammen aus dem Offer-JSON (`bookingsequence` = `hotel.product`, `date` = `arrivalDate` als TT.MM.JJJJ). Auf der Seite nur im Checkout sichtbar, aber direkt aufrufbar. |
| **Live-Bestätigung (vacancy-check)** | **POST** `https://d2z3tkv1undzra.cloudfront.net/vacancy-check` (JSON-Body, gleicher Host wie Offer-API, kein Login) | Das, was der Knopf „Verfügbarkeit prüfen" auf tui.com auslöst. Body wird aus dem Offer-JSON gebaut (`_build_vacancy_payload()`): `scope/tenant/locale` + Konstanten `agency:"021245"`, `agent:"0000"`, `channel:"TUIIA"` + `offer{tempId, startDate, checkInDate, nights, hotel, programType, currency, cancellationType, travelType, departureFlight, returnFlight, rooms[], price{totalNetPrice,…}}`. **Stolperfalle:** `travelType` muss ein **Objekt** `{code,brand,tourOperator,bookingTourOperator}` sein (im Offer-JSON ist es nur ein String) — sonst `status:"FAILED"`. `campaignData`/`meta`/`tracingId` sind optional (live verifiziert). Antwort: `status` (`OK`/`FAILED`), **Preis-Aufschlüsselung** `hotel.rooms[].travellers[].price` + `outboundFlight`/`inboundFlight.travellers[].price` (Summe = `totalPrice`), `seatReservable`, Buchungsklassen, `system:"ATCOMRES"` (live aus dem Veranstaltersystem). Code: `_fetch_vacancy()`. |
| **Inklusiv-Gepäck** | **POST** `https://api.cloud.tui.com/flight-luggage-api/get`, Body `[{airline,route:"STR-RHO",organizer}]` je Flug | `[{luggage:{adult:{pcs,weight}},state:"OK"}]`. Code: `fetch_luggage()`. |
| **Zuletzt gebucht** | `https://d3hw3spwqlykxv.cloudfront.net/hotel-last-booked/TUICOM/<giataId>` | `{date, in_the_last_24_hours}` — Nachfrage-Signal. Code: `_fetch_last_booked()`. |
| **Zahlungskonditionen** | **POST** `https://www.tui.com/api/paymentService/payments` — braucht Header **`X-Agency: 021245`** (sonst HTTP 400 "insufficient headers") | Body: `{tenant:"tuicom", cancellationType, isOmnichannel:false, isPackagetour:true, services:[{system:"ATCOMRES", tourOperator, startDate, countryCodes:["GR"], productCodes:[hotel.product]}]}`. `countryCodes` ist Pflicht; der ISO-Code kommt aus dem Hotel-Content-Endpoint `https://d2tzlxlrauxuk9.cloudfront.net/data?giataId=…` → `contact.address.countryCode`. Antwort: Zahlarten, `depositPercentage` (Anzahlung), `finalPaymentDate` (Restzahlung). Code: `fetch_payment_terms()`. |
| **Preiskalender** | `https://d18axsujemfwj.cloudfront.net/data?giatas=…&duration=…&adults=…&startSearchRange=…&endSearchRange=…&airports=…&roomTypeOpCodes=…&boardCodes=…&tourOperators=…&startDate=…&endDate=…` | `offers[]` je `arrivalDate` → `calculatedPricePerPerson`; min pro Tag = „ab"-Preis. **Achtung:** dieser Endpoint nutzt **andere** Parameternamen als der Offer-Endpoint: Verpflegung = `boardCodes` (nicht `boardTypes`), Veranstalter = `tourOperators` (nicht `operators`), Personen = `adults`, giataId = `giatas`. `startDate/endDate` = sichtbarer Rasterbereich (wir nehmen Suchzeitraum ±7 Tage). |
| **Hotelsuche (Region)** | **POST** `https://api.cloud.tui.com/hotel-offer-cards/v2/search/TUICOM` (JSON-Body, stabiler Host) | Body: `{"parameters":{searchScope,startDate,endDate,duration:[N],rooms:[{numberOfAdults,childAges,roomCodes,boardCodes}],airports:[],tourOperators:[],giataRegions:[…],sortingOrder:"priceAsc",resultsPerPage,resultsFrom,resultsTotal,transferIncluded:false,identifier:"HLP"}}`. `sortingOrder` bewusst `"priceAsc"` (nicht `"qualifier2DESC"`/Best-Match-Score) — bei mehr Treffern als `resultsPerPage` (z. B. 256 in einer Region, nur 50 abgeholt) fehlten sonst die günstigsten Hotels komplett im abgeholten Batch, egal wie clientseitig sortiert wird (Bugreport, live gegen tui.com selbst per `sortHotelsField=price&sortHotelsAsc=1` verifiziert). Antwort: `resultsTotal` + `items[]` mit `hotel{giataId,name,category(=Sterne),location{country,region,city,lat,lng},holidayCheckRecommendationRate,holidayCheckNumberOfCurrentReviews,brand,images[]}`, `price{perPerson{amount,originalAmount},advantage(=Rabatt %, negativ)}`, `boardType`/`boardCodes`(Kurzcodes wie `AI`), `roomOpCode`, `numberOfNights`, `startDate`. **Region zuerst wählen:** `giataRegions` stammt aus `regionGiataIds` der Such-/Region-URL **oder** — für die Suche aus einem bestehenden Angebot — aus der **Breadcrumb-API** über die Hotel-`giataId`: der **letzte `level==1`-Eintrag** ist die Region/Insel (`region_giata_from_breadcrumb()`; Gran Canaria=128, Kap Verde=88). Such-API akzeptiert **Land-, Region- und Insel-Ebene**, **nicht** reine Stadt-Ebene (HTTP 400). Treffer verlinken auf die normalen `…/angebote/<Hotel>/<giataId>/offer/`-URLs → direkt trackbar (`offer_url_for`). **Pagination:** `resultsFrom` (= `offset`-Parameter durchgereicht bis `_run_search()`/`fetch_search()`/`fetch_search_params()`) holt die nächste Seite ab diesem Treffer-Index — ein Aufruf liefert nie mehr als `resultsPerPage` (50) Treffer, egal wie hoch `resultsTotal` gesetzt ist (live verifiziert). `POST /api/search` mit `offset` im Body nutzt das für den "Mehr laden"-Button im Frontend (`loadMoreSearch()` in app.js), hängt die neue Seite an `srchResults` an statt sie zu ersetzen. **Filter gehören in die Anfrage, nicht in einen Nachfilter:** Sterne, Weiterempfehlung und Höchstpreis kennt die API selbst — `"category": 4` (ZAHL, „ab 4 Sonnen"; Liste oder String → HTTP 400), `"recommendations": [{"name":"recommendationsTotal","operator":"gt","value":80}]` und `"maxPrice": 1500` (pro Person). Feldnamen aus einem Mitschnitt der echten tui.com-Suchseite (dieselbe API; Playwright, `page.on('request')` auf `hotel-offer-cards`), Trefferzahlen live gegengeprüft: 272 → 206 (`category`) → 135 (+ `recommendations`) — die Website zeigt für dieselben Filter exakt 135. Vorher liefen diese drei als Nachfilter über die abgeholte Seite; da `sortingOrder` preisaufsteigend ist, stehen in den ersten 50 Treffern fast nur einfache Hotels und ein 4-Sterne-Filter ließ davon eine Handvoll übrig. Code: `_run_search()`/`fetch_search()`/`fetch_search_params()` in [scraper.py](scraper.py). |
| **Reiseziel-Picker** | `GET https://api.cloud.tui.com/search-destination/v2/de/package/TUICOM/giata/regions` (Top-Level) bzw. `…/giata/subregions/<giataId>` (Drilldown) | `{items: {<giataId>: {label, level}}}` (+ `parentName` bei Subregionen). Drilldown Land→Region→Insel; alle Ebenen außer Stadt sind als `giataRegions` suchbar. Code: `fetch_destinations()`. |
| **Reiseziel-Index (globale Suche)** | dieselben Endpunkte, aber **rekursiv** über den ganzen Baum (~1000+ Aufrufe) | Flacher Index `[{giata, label, path}]` mit Breadcrumb-Pfad. Wegen der Last nur **gecacht** verwenden: Aufbau beim Start im Hintergrund, persistiert in der DB (`meta.dest_index`), Neuaufbau alle 14 Tage bzw. manuell (`POST /api/destinations/reindex`). Code: `build_destination_index()`. |
| **Abflughäfen** | `GET https://api.cloud.tui.com/search-departure-airport/v2/departureAirports/TUICOM/de-DE` | Liste `[{key(=IATA, z. B. STR), name, geolocation, preselected}]`. Code: `fetch_airports()`. |
| **Fluggesellschaften** | *kein offener Endpunkt* — **kuratierte Liste** `TUI_AIRLINES` in [scraper.py](scraper.py) (IATA-Codes wie `EW`,`DE`,`X3`). Code: `fetch_airlines()`. | Optionaler Filter. Codes gehen als `airlines` in den Such-POST (Liste) und in die Offer-/Such-URL (mehrere mit **`;`** getrennt, z. B. `airlines=X3;VY`); die Offer-/Preis-API filtert die Flüge entsprechend. |

- Die **giataId** steht im Pfad der Seiten-URL: `…/angebote/<Hotel>/<giataId>/…`.
- `build_offer_api_url()` mappt die Seiten-Parameter → API-Parameter (u. a.
  `duration`→`durations`, `departureAirports`→`airports`); der **eingegebene
  Reisezeitraum** (`startDate`/`endDate`/`duration`) wird dabei übernommen.
- `cheapest: true` markiert die günstigste Karte direkt — kein Heuristik-Raten.
- **Flugvarianten (v0.91.0):** Die `offers[]` desselben Abrufs unterscheiden sich oft
  nur im Flug (Airline, Uhrzeit, Zwischenstopps, teils Anreisetag) — verfolgt wird
  weiterhin genau eine Variante, alle werden aber als `flight_options` mitgeliefert
  (`_flight_options()`, Aufpreis `delta` gegenüber der verfolgten Variante) und am
  Angebot als JSON gespeichert. Eine Variante lässt sich **fixieren**: `flight_pin`
  enthält den Schlüssel `_flight_key()` = `Airline-Code|Stopps|HH:MM|Anreisedatum`;
  `fetch_price_api(..., flight_pin=…)` nimmt dann das günstigste Offer mit diesem
  Schlüssel. Kein Treffer → `flight_pin_missed=True`, Fallback auf den günstigsten
  Flug (`check_offer()` löst dann die Fixierung und schreibt ein Angebots-Ereignis).
  Bewusst **nicht** über URL-Filter gelöst: `departureMinTime`/`departureMaxTime`/
  `returnMinTime`/`returnMaxTime` werden von der Angebots-API **ignoriert** (live
  gegengeprüft, `HH:MM` und Minuten) — wirksam sind nur `maxStopOvers` und
  `airlines`, die den Anreisetag aber nicht unterscheiden können.
- **Zimmerauswahl:** ohne `roomTypeOpCodes` liefert der Offer-Endpoint alle Zimmer; wir
  gruppieren die `offers[]` nach `rooms[0].code` (z. B. `DZM1`/`DZM3`) und nehmen je
  Zimmer den günstigsten `calculatedPricePerPerson` (Name = `rooms[0].description`). Ein
  fixes Zimmer wird über `roomTypeOpCodes=<code>` in der Angebots-URL verfolgt
  (`fetch_rooms()`/`with_room_code()`/`room_code_from_url()`). Langtext/Fotos hat die API
  nicht — dafür verlinkt das UI das Zimmer auf tui.com.
- **Hotelbild:** Nur die **Such-API** liefert `hotel.images[0].url` (pics.tui.com). Offer-/
  Content-API haben kein Bild. `fetch_hotel_image()` bestimmt daher die Region über den
  Breadcrumb, sucht in ihr und nimmt das Bild des Treffers mit passender giataId
  (einmalig je Angebot, danach in `offers.image_url` gecacht). Serverseitiger Bildabruf
  gibt 403 (Hotlink-Schutz) → Bild nur als `<img>` im Browser, nie serverseitig laden.
- **Dauer-Bereiche** (`duration=7-`, `9-12`): der **Kalender** braucht eine *einzelne*
  Dauer → wir nehmen die untere Zahl (`_single_duration()`). Der **Offer**-Abruf bekommt
  den Bereich unverändert (`durations`), damit der günstigste über alle Dauern stimmt.
- **Kalender-Fenster / Paginierung:** Die Kalender-API liefert pro Aufruf nur ein
  begrenztes Fenster (~12 Monate ab `startSearchRange`) und ignoriert ein weit gesetztes
  Ende. `fetch_calendar()` ruft `build_calendar_api_url(url, start=…, end=…)` daher wie
  die TUI-Seite **mehrfach** auf — ab heute jeweils weiter ab dem zuletzt gelieferten
  `arrivalDate`+1 bis über das Reiseende hinaus — und führt die Tage zusammen (volle
  Spanne aktueller Monat … Inventarende).
- **Verbose-Log:** bei `verbose_log` werden alle API-URLs + Ergebnisse über den Logger
  ausgegeben (erscheinen in der UI-Konsole) — Scraper nutzt `logging`, kein `print`.
- **Wichtig: alle Filter der Original-URL durchreichen** (`boardTypes`, `operators`→
  `tourOperators`, `roomTypes`, `viewTypes`, `roomTypeOpCodes`, Preisgrenzen). Fehlt
  ein Filter, liefert die API u. U. ein anderes/billigeres Angebot (z. B. Halbpension
  statt AI). Die Verpflegungs-Kurzcodes werden dabei ins API-Schema übersetzt:
  `AI`/`HB`/`FB`/`AO` → unverändert `GT06-<code>`, **außer `BB` (Frühstück) → `GT06-BR`**
  — die Angebots-/Kalender-API nutzt intern `BR` statt `BB`, an 3 Hotels live
  verifiziert (`_map_board_types()`, `_BOARD_CODE_ALIASES`). Ohne diese Übersetzung
  liefert die API 0 Treffer und das Angebot erscheint fälschlich als "nicht
  verfügbar" (betraf Preis-, Kalender- und Zimmer-Abruf gleichermaßen, da alle
  über `build_offer_api_url()`/`build_calendar_api_url()` laufen).

**Risiko / Wartung:** Die CloudFront-Hostnamen (`d2z3tkv1undzra…`, `d1pagbczmuq2ek…`)
sind opak und könnten rotieren. Passiert das, liefert die API einen Fehler →
automatischer **Browser-Fallback** (unten). Neue Hosts findet man, indem man die
Seite mit Playwright lädt und die `response`-URLs mit `/data?` + `giataId=` und
JSON-Body mit `offers`/`price` mitschneidet (so wurden sie ermittelt). Dann
`OFFER_API`/`CONTENT_API` in [scraper.py](scraper.py) aktualisieren.

## Fallback: Browser (Headless-Chromium)

Greift nur, wenn die JSON-API technisch fehlschlägt. Hintergrund, warum überhaupt ein
Browser nötig war:
- Die Angebotsseite liefert per **statischem HTTP-Abruf der HTML-Seite keinen Preis** –
  der Preis wird erst per JavaScript nachgeladen (kein `__NEXT_DATA__`/JSON-LD im HTML).
- Fallback-Lösung: Seite mit **Headless-Chromium (Playwright)** rendern und das DOM
  auslesen. Code: `_fetch_price_browser()` in [scraper.py](scraper.py).

**Zwei Bremsen davor** (seit 0.113.11), weil der Browser teuer ist — gemessen rund
400 MB leer und bis 740 MB mit geladener TUI-Seite, verteilt auf sechs bis sieben
Prozesse, die im Add-on alle zum Speicher des Containers zählen:
- `browser_fallback_enabled()` — Einstellung *Browser-Fallback (Chromium)*, Standard an.
  `scraper.py` kennt die Einstellungen nicht (es läuft auch als eigenes Skript und in den
  Parsing-Tests); `app.py` hängt beim Start eine Funktion ein, die den Wert bei jedem
  Aufruf frisch liest — Umschalten wirkt also ohne Neustart.
- `internet_reachable()` — TCP auf `www.tui.com:443` und `1.1.1.1:443`, 4 s. Zwei feste
  Ziele, absichtlich nicht aus der Angebots-URL abgeleitet: geprüft wird die Leitung,
  nicht ein vom Benutzer benannter Host. Ohne Netz ist auch die gerenderte Seite nicht
  zu holen — der Browser bliebe 740 MB für nichts, und das bei jedem fälligen Angebot
  nacheinander.

Jedes gestartete Chromium bekommt zusätzlich `--tuiwatch-fallback` in die Kommandozeile
(`BROWSER_MARKER`). Chromium ignoriert das Flag; für uns ist es das Erkennungszeichen,
an dem `_reap_orphan_chromium()` in [app.py](app.py) einen hängengebliebenen Browser
zweifelsfrei von einem fremden im selben Namensraum unterscheidet. Aufgeräumt wird bei
jeder Poll-Runde und nie, solange `scraper.browser_busy()` einen laufenden Abruf meldet.

Denselben Test nutzt der Poller einmal je Runde (`_net_ok()` in [app.py](app.py)): ohne
Netz pausieren Preisprüfungen, Suchabos, Kalender, Selbsttest, Aktionscodes und
Wochenbericht, während örtliche Schritte (Backup, Preisbarometer) weiterlaufen. Der
Ausfall steht einmal im Log, danach höchstens stündlich, die Rückkehr wieder einmal.

## Was wird ausgelesen (Stand: 2026-06, funktioniert)

Wichtig: Es gibt **zwei** Preise auf der Seite.
- Die **„Dein Angebot"-Box** (`div.tui-hotel-best-offer`) zeigt nur einen
  *„ab"-Lockpreis* (z. B. 1.933 €) — **den nutzen wir NICHT mehr**, nur als
  Lade-Signal, dass die Seite fertig ist.
- Getrackt wird die **erste (= günstigste) konkrete Angebotskarte**
  `div.offer-card__content` (Liste ist aufsteigend sortiert via URL-Param
  `sortOffersAsc=1`). Das ist der echte, buchbare „Günstigster Preis"
  (z. B. 1.978 €) inkl. Flugdetails.

| Datum | Selektor / Logik | Beispielwert |
|---|---|---|
| Lade-Signal | `div.tui-hotel-best-offer` (nur warten) | – |
| Konkrete Karte | erste `div.offer-card__content` mit „pro Person" + € | – |
| Preis p. P. | Regex `pro Person <Zahl> €` in der Karte | `1978` |
| Alter Preis + Rabatt | Regex `<N>% <Zahl> €` (z. B. „- 7% 2.129 €") | `2129`, `7` |
| Zimmer | Kartenzeile mit Raumcode `(…\d…)`, z. B. `(DZX1)` | `Double Room with Garden View (DZX1)` |
| Verpflegung | Zeile aus `BOARD_TYPES` | `Alles Inklusive` |
| Nächte / Reisende | Regex `\d+ Nächte` / `\d+ Erwachsene(r)` | `10 Nächte`, `1 Erwachsener` |
| Abflughafen | erste Zeile `… (XXX)` (3 Großbuchstaben) | `Stuttgart (STR)` |
| Flug Hin/Rück | Zeilen mit `TT.MM.JJJJ, HH:MM` + Airline + `Direktflug`/Stopps | `Fr., 07.05.2027, 13:30 Uhr · TUIfly · Direktflug` |
| Hotelname | `h1.tui-hotel-name__title` | `Riu Papayas` |
| Verfügbarkeit | Button `button:has-text('Verfügbarkeit')` in der Karte klicken → Text „verfügbar"/„nicht verfügbar" | `true`/`false` |
| Cookie-Consent | erster sichtbarer aus `#cmm-accept-all`, `#onetrust-accept-btn-handler`, `button:has-text('Alle akzeptieren')` u. a. | – |

Hotelname-**Fallback**, falls die Überschrift fehlt: aus der URL ableiten – das
Segment hinter `/angebote/` (`Riu-Papayas` → `Riu Papayas`). Siehe
`hotel_from_url()` in [scraper.py](scraper.py).

Alle Selektoren/Regexe stehen als Konstanten oben in [scraper.py](scraper.py)
(`OFFER_CARD_SELECTOR`, `BEST_OFFER_SELECTOR`, `HOTEL_NAME_SELECTOR`,
`CONSENT_SELECTORS`, `_PRICE_RE`, `_OLDPRICE_RE`, `_AIRPORT_RE`, `_ROOMCODE_RE`,
`_FLIGHTLINE_RE`, `BOARD_TYPES`). Parsing-Logik: `_parse_card()` / `_parse_flights()`.

## Stolperfallen (wichtig fürs Debuggen)

- **`page.inner_text("body")` liefert fast nichts** (~680 Zeichen), obwohl die Seite
  voll gerendert ist. Inhalt nicht über `body`-Text suchen, sondern gezielt über
  Selektoren / `query_selector_all`.
- **`networkidle` läuft regelmäßig in den Timeout** – das ist normal, einfach weiter.
  Wir warten primär auf `div.tui-hotel-best-offer`.
- **Deutsches Zahlenformat:** `.` = Tausender, `,` = Dezimal → `_to_amount()`.
  Das `€` kann ein geschütztes Leerzeichen (`\xa0`) davor haben.
- Es gibt einen **zweiten Frame** (`review-service.holidaycheck.com`) – Bewertungen,
  **nicht** der Preis. Im Hauptframe (`page.main_frame`) arbeiten.
- **Bot-Schutz:** realistischen User-Agent + `locale="de-DE"` setzen (machen wir);
  Intervall nicht zu klein wählen (`MIN_POLL_INTERVAL` in app.py).

## Wenn TUI das Layout ändert — so neu kalibrieren

Symptom: im Verlauf erscheinen Einträge mit `ok=0` und Hinweis „Angebots-Box nicht
gefunden" oder „Endpreis nicht erkannt" (in der Konsole / Verlauf-Tabelle sichtbar).

1. **Probe-Skript ausführen** (rendert die Seite sichtbar-nah und dumpt Kandidaten).
   Minimal-Variante, lokal mit installiertem Playwright:

   ```python
   import time
   from playwright.sync_api import sync_playwright
   URL = "<deine TUI-Angebots-URL>"
   UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
         "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
   with sync_playwright() as p:
       pg = p.chromium.launch().new_context(locale="de-DE", user_agent=UA,
            viewport={"width":1366,"height":1800}).new_page()
       pg.goto(URL, wait_until="domcontentloaded", timeout=60000); time.sleep(2)
       for s in ["#cmm-accept-all","#onetrust-accept-btn-handler",
                 "button:has-text('Alle akzeptieren')"]:
           el = pg.query_selector(s)
           if el and el.is_visible(): el.click(); break
       time.sleep(5)
       pg.screenshot(path="probe.png", full_page=True)          # visuell prüfen
       # a) Hotelname
       for el in pg.query_selector_all("h1"):
           print("H1:", (el.get_attribute("class") or ""), "→", (el.inner_text() or "")[:80])
       # b) Preis-Kandidaten: alle Elemente mit € und kurzem Text
       for el in pg.query_selector_all("[class*='price' i],[data-testid*='price' i]"):
           t = (el.inner_text() or "").strip().replace("\n"," ")
           if "€" in t and len(t) < 60:
               print("PRICE:", el.get_attribute("class") or el.get_attribute("data-testid"), "→", t)
   ```

2. **Im Screenshot `probe.png`** die „Dein Angebot"-Box identifizieren. Den
   Container-Selektor findet man, indem man vom Preis-/Überschrift-Element die
   Vorfahren hochläuft (`el.evaluate("e=>{...parentElement...}")`) und einen stabilen
   `class`/`data-testid` sucht (so haben wir `div.tui-hotel-best-offer` gefunden).

3. **Selektoren in [scraper.py](scraper.py) anpassen** (`BEST_OFFER_SELECTOR`,
   `HOTEL_NAME_SELECTOR`, ggf. die Regexe / `CONSENT_SELECTORS`).

4. **Lokal testen** (ohne ganzes Add-on):
   ```
   python scraper.py "<TUI-URL>"
   ```
   Erwartete Ausgabe: JSON mit `ok: true`, korrektem `price`, `hotel`, `details`.

5. Add-on lokal gegenprüfen (siehe README/DOCS: Env-Vars `TUIWATCH_BASE/DATA/PORT`,
   Login `admin/secret`, URL einfügen, „Prüfen").

## Lokale Testumgebung (Kurzform)

```
$env:TUIWATCH_BASE="<…>\tuiwatch"
$env:TUIWATCH_DATA="<…>\tuiwatch\dev_data"
$env:TUIWATCH_PORT="17794"
python app.py    # http://127.0.0.1:17794  ·  admin / secret
```
Playwright nutzt lokal sein gebündeltes Chromium; im Container wird über die
Umgebungsvariable `CHROMIUM_PATH` das System-Chromium gesetzt.
