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

- Die **giataId** steht im Pfad der Seiten-URL: `…/angebote/<Hotel>/<giataId>/…`.
- `build_offer_api_url()` mappt die Seiten-Parameter → API-Parameter (u. a.
  `duration`→`durations`, `departureAirports`→`airports`); der **eingegebene
  Reisezeitraum** (`startDate`/`endDate`/`duration`) wird dabei übernommen.
- `cheapest: true` markiert die günstigste Karte direkt — kein Heuristik-Raten.

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
