# Check24-Vergleich — Scraping-Notizen (Phase-0-Spike)

Pendant zu [SCRAPING.md](SCRAPING.md), aber für den optionalen Check24-Preisvergleich
(`enable_check24_compare`). Anders als TUI hat Check24 **kein offenes, stabiles
JSON-API** — die Hotel-Angebotsseite ist eine JS-SPA mit asynchronem Job/Poll-Protokoll
und **verschlüsselter Nutzlast**. Dieses Dokument hält fest, was per Playwright
(Response-Interception + DOM-Dump) am echten Beispiel „Gloria Palace Amadores
Thalasso & Hotel" (hotelId=11829, areaId=551, Gran Canaria) und „Servatur Waikiki"
(hotelId=3611) ermittelt wurde.

## Entscheidung: Pfad B (Playwright, gerendertes DOM)

Pfad A (reines `requests`, kein Browser) ist **kein gangbarer Weg für die
Preis-/Zimmer-/Verpflegungsdaten** — siehe unten. Der einzige praktikable Weg ist,
Check24s eigenes JS die Verschlüsselung auflösen zu lassen (echter Browser-Kontext)
und danach das **gerenderte DOM** abzugreifen, exakt wie `scraper.py`s
Playwright-Fallback für TUI (`scraper.py:1313+`) es für den Notfall bereits tut —
nur dass es hier der einzige Weg ist, nicht der Fallback.

## Der Seitenaufbau (3 Ebenen)

### Ebene 1 — Regionsergebnisse (SSR, per `curl` lesbar)

```
GET https://urlaub.check24.de/suche/region?departureDate=YYYY-MM-DD&returnDate=YYYY-MM-DD
    &days=exact&roomAllocation=A-A&airport=&transportType=flight&...
```

Reines server-seitig gerendertes HTML, kein JS nötig. Zeigt eine Liste von
Reisezielen/Regionen, keine einzelnen Hotels. Für den Check24-Vergleich **nicht
gebraucht** (wir suchen hotelId-spezifisch), aber bestätigt: der Sidebar-Filter
für Verpflegung/Zimmer/Aussicht/Flug/Abflugzeit existiert wirklich (UI-Labels
bestätigt, Query-Param-Namen nicht extrahiert — nicht nötig für unseren Ansatz,
da wir client-seitig nach Board/Room filtern statt über Query-Params).

### Ebene 2 — Hotel-Ergebnisliste (JS-SPA, `xsearchd`-Poll) — **umgangen, s. u.**

```
GET https://urlaub.check24.de/suche/hotel?airport=STR&transportType=flight
    &roomAllocation=A&departureDate=2027-04-28&returnDate=2027-05-09&days=exact
    &pageArea=package&areaId=551&dhs=11829&ds=h&sorting=categoryDistribution
    &offerSort=offerRanking&areaSort=topregion&extendedSearch=1&noRedirect=1
    &hotelId=11829
```

Kein SSR — `curl` liefert nur ein leeres App-Gerüst. Playwright zeigt: die Seite
feuert `GET /xsearchd/<n>/poll?clientId=<uuid>` wiederholt, Antwortform:

```json
{"data":{"status":"updated","events":[{"type":"hds_hotel_list","status":"updated","total":5,"finished":0}]},
 "status":{"http":{"message":"OK","code":200},"percentage":15},"success":true}
```
… bis `status:"finished"`, `finished==total`, `percentage:100`.

Sobald fertig, zeigt die Seite pro Hotel **eine** Karte mit **einem** Ab-Preis
+ „zu den Angeboten"-Button — **keine** Anbieter-Aufschlüsselung auf dieser Ebene.
Falls die exakten Wunschtermine für das gepinnte Hotel nicht verfügbar sind,
erscheint „Leider schon weg! Ihre Reisedaten sind beliebt!" mit bis zu 4
alternativen Terminen (nur Ab-Preis, kein Angebots-Link) — **das ist
Datenverfügbarkeit, kein Protokollfehler** (in mehreren Testläufen beobachtet,
je nach gewähltem Datum).

**Wichtiger Nachtrag:** `areaId`/`dhs` sind gar nicht nötig. Ein `curl` auf
Ebene 2 **ohne** `areaId` (nur `hotelId=11829`) liefert `HTTP 200` und wird vom
Server automatisch auf `.../suche/angebot?...&hotelId=11829&...` weitergeleitet
— also direkt auf Ebene 3, die eigentliche Vergleichsseite. `check24_client.py`
ruft daher nur noch `hotelId` auf (`_build_offer_url()`), Ebene 2 wird in der
Implementierung gar nicht mehr separat geladen, der „zu den Angeboten"-
Popup-Klick (inkl. `hotelListId`) entfällt komplett.

### Ebene 3 — Hotel-Angebotsseite (der eigentliche Vergleich)

Auf `/suche/angebot?...` feuert die Seite:

```
GET https://urlaub.check24.de/suche/json/dynamic/offer?<gleiche Query-Params>
```
→ Job-Erzeugung, Antwort:
```json
{"status":"Pending","tourOperatorList":{},"pollUrl":"https://urlaub.check24.de/offersearch/29/poll",
 "needsPolling":true,"meta":{"hotelName":"Servatur Waikiki","regionName":"Gran Canaria", ...}}
```

Dann Poll:
```
GET https://urlaub.check24.de/offersearch/<jobId>/poll?clientId=<uuid>&step=offerList
```
→ mehrere Events parallel (`filter_information`, `offer_list`, `price_calendar`,
`vacancy`), jedes mit eigenem `status`/`total`/`finished`. Fertig, wenn
`offer_list.status=="finished"` (in unserem Test: `total:8, finished:8`).

Erneuter `GET /suche/json/dynamic/offer?...` liefert dann `items`, ein Dict pro
Angebot:
```json
{"1405863043799753169":{"id":"...","hotelId":3611,"tourOperatorCode":"ITSX",
                          "supplierCode":"tt","cryptString":"0I4FXUtS...(sehr lang, verschlüsselt)"}}
```

**`cryptString` ist die eigentliche Preis-/Zimmer-/Verpflegungs-Nutzlast, aber
verschlüsselt.** Es gibt keinen erkennbaren Klartext-Preis in diesem JSON — nur
`tourOperatorCode` ist im Klaren lesbar. Das serverseitige Entschlüsseln/Reversen
dieses Formats wurde **bewusst nicht versucht** (hoher Aufwand, hohes
ToS-/Anti-Bot-Risiko, vermutlich rotierende Schlüssel) — das ist der Grund für
die Pfad-B-Entscheidung oben.

**Das gerenderte DOM zeigt die entschlüsselten Daten im Klartext**, da Check24s
eigenes Frontend-JS `cryptString` im Browser auflöst. Bestätigtes Beispiel
(Playwright, nach Abwarten bis `offer_list` fertig ist), eine Angebotskarte:

```
12 Tage | 11 Nächte Stuttgart (STR) ↔ Las Palmas (LPA)
Do, 22.04.2027 | 1 Stopp   10:50 Stuttgart → 16:50 Las Palmas
Mo, 03.05.2027 | 1 Stopp   10:25 Las Palmas → 18:35 Stuttgart
1x Doppelzimmer Standard
DB1 - Double Room Classic
Frühstück
Hotel-Transfer
Balkon/Terrasse
nur Handgepäck
Stornierung kostenpflichtig
1.529,00 €
zur Buchung
```

Mehrere solcher Karten pro Seite (verschiedene Operator/Zimmer/Verpflegungs-
Kombinationen für dasselbe Hotel+Termin), Preise beobachtet zwischen
1.511,00 € und 1.607,00 € je nach Zimmerkategorie/Transfer/Gepäck-Optionen.

Die **Veranstalter-Filterliste** in der Sidebar (Ebene 3) bestätigt echte
Operator-Vielfalt für dieses Hotel: „Alltours Dynamisch", „AurumTours",
„DERTOUR Dynamisch", „FERIEN Touristik", „ITS Dynamisch" (+ weitere, „alle 7
anzeigen"). Ein Verpflegungs-Filter existiert ebenfalls direkt auf dieser Ebene
(„Ohne Verpflegung" / „Mind. Frühstück" / „Mind. Halbpension" / „Mind.
Vollpension" / „mind. All Inclusive").

**Gelöst:** der Operator-Name steht als Klartext im `alt`-Attribut eines
`img.operator-img` innerhalb jeder Angebotskarte (z. B. `alt="ITS Dynamisch"`,
`"DERTOUR Dynamisch"`, `"alltours dynamisch"`, `"LMX Touristik"`) — direkt
lesbar, keine Code→Name-Übersetzung nötig. Die einzelne Angebotskarte ist als
`li.price-offer.js-offer-box` im DOM abgrenzbar (per Ancestor-Chain vom „zur
Buchung"-Button verifiziert), enthält aber selbst >100 KB `innerText`
(versteckte Alternativ-Termine etc.) — zu unzuverlässig für direktes Preis-
Parsing pro Karte. `check24_client.fetch_offers()` liest daher **zwei
getrennte, leichtgewichtige Signale**, die sich per Reihenfolge korrelieren
lassen: (1) Preis/Zimmer/Verpflegung weiterhin aus dem kompletten Seitentext
via `_parse_offer_blocks()` (bewährt), (2) je Karte nur `querySelector(
'img.operator-img').alt` (ein kurzer String, kein Massentext) via
`eval_on_selector_all('li.price-offer.js-offer-box', ...)`. Beide Listen sind
in Seitenreihenfolge, werden vor jeglichem Filtern/Sortieren per Index gezippt.
**Bekannte Schwäche:** die Roh-Kartenzahl (`li.price-offer.js-offer-box`, z. B.
27) und die aus dem Fließtext geparste Zeilenzahl (z. B. 25) stimmen nicht
immer exakt überein (vermutlich einzelne Alternativ-Termin-Karten ohne
eigenen Preis-Textblock) — bei Abweichung bekommen die überzähligen Zeilen
keinen Anbieternamen (leerer String), keine Fehlzuordnung, aber ggf. Lücken.

**Zusätzlich:** `fetch_offers()` gibt jetzt `offer_url` zurück (die
Angebotsseiten-URL selbst, `_build_offer_url()`) — kein Deep-Link auf die
exakte Zimmer-/Anbieter-Zeile (der „zur Buchung"-Button hat leeres `href`,
JS-Navigation ohne statischen Link), aber ein direkter Klick-Link zur
Check24-Seite für dieses Hotel/diese Reisedaten.

## Hotel-Suche ohne manuellen Link (Autocomplete)

Das Zielsuchfeld auf `https://www.check24.de/pauschalreisen/` (`#c24-travel-
destination-element`) liefert beim Tippen eines Hotelnamens **clientseitig**
(kein Server-Roundtrip beobachtet) eine Vorschlagsliste, in der Hotel-Treffer als
`<li class="c24-travel-hotelfilter-item"><a data-item-id="11829" ...>` erscheinen
— `data-item-id` **ist die `hotelId`**. Bestätigt am Beispiel: Tippen von „Gloria
Palace Amadores" → Vorschlag „Gloria Palace Amadores Thalasso & Hotel" mit
`data-item-id="11829"` (identisch mit dem bekannten Beispiel-hotelId). `check24_
client.search_hotel()` nutzt genau das, damit Nutzer:innen **keinen** Check24-Link
von Hand kopieren müssen — der TUI-Hotelname aus dem Angebot wird automatisch
eingetippt (per `page.fill()`), keine Nutzereingabe nötig.

Die Autocomplete matched wortweise (nicht nur Gesamtname) — ein langer TUI-
Hotelname liefert oft 15-20 kaum verwandte Treffer (z. B. alle Hotels mit
„Palace" im Namen). `search_hotel()` sortiert daher per `difflib.SequenceMatcher`
nach Ähnlichkeit zur Anfrage und reduziert auf den Top-Treffer, wenn dieser
eindeutig ist (Score ≥0.92, Abstand zum Zweitplatzierten ≥0.08) — sonst bleibt
die volle Liste zum Anklicken.

## Zusammenfassung für `check24_client.fetch_offers()`

1. Playwright-Kontext öffnen.
2. Direkt Ebene 3 laden: `/suche/hotel?hotelId=<id>&departureDate=&returnDate=
   &airport=&roomAllocation=&transportType=flight&days=exact&...` (kein
   `areaId`/`dhs` nötig, s. o. — Server leitet automatisch weiter). Fixe
   Wartezeit ~12s nach `domcontentloaded` (Poll-Requests wurden in Testläufen
   nicht zuverlässig beobachtet, siehe „Bekannte Instabilitäten"), danach
   Cookie-Consent-Layer entfernen
   (`document.querySelectorAll('.c24-cookie-consent-wrapper').forEach(e=>e.remove())`).
3. Sichtbaren Seitentext prüfen: „schon weg" **und** keine Angebotskarte im
   Text → `{'ok': True, 'rows': [], 'note': 'not_available_exact_dates'}`
   (Datenverfügbarkeit, kein Fehler).
4. Angebotskarten aus dem Seitentext per Regex extrahieren (Zimmertyp,
   Verpflegung, Preis) — `_parse_offer_blocks()`, siehe Quellcode.
5. Nach `board_hint`/`room_hint` (Substring, case-insensitive) filtern, günstigste
   passende Zeile(n) zurückgeben.

## Bekannte Instabilitäten (beobachtet, nicht vollständig erklärt)

- Kaltes Laden derselben Ebene-2-URL zeigte in Testläufen mal ein isoliertes
  Einzelhotel-Ergebnis (mit `xsearchd`-Poll `total:5`), mal eine breite
  Regions-Trefferliste (1000+ Hotels) mit dem Zielhotel nur hervorgehoben oben —
  vermutlich abhängig davon, ob Such-/Session-Cookies aus einem vorherigen
  Seitenaufruf vorhanden sind. Für den Scraper unkritisch, solange Ebene 3 (das
  eigentliche Ziel) über den „zu den Angeboten"-Link erreicht wird, nicht über
  geratene Parameter.
- Manche Testläufe zeigten 0 `xsearchd`/`offersearch`-Poll-Requests trotz
  sichtbarer Ergebnisse — vermutlich Job bereits vor Listener-Anmeldung
  abgeschlossen (schnelle Antwort) oder Cache-Treffer. Für die Implementierung:
  nicht auf das Vorhandensein von Poll-Requests verlassen, sondern auf das
  Endergebnis im DOM warten (Selector-Wait / Timeout), das Poll-Protokoll nur als
  Fortschrittsanzeige nutzen falls beobachtbar.

## Risiko-Hinweis

Verschlüsselte Nutzlast (`cryptString`) ist ein klares Signal, dass Check24
aktiv gegen automatisiertes Auslesen absichert. Playwright-DOM-Scraping (Pfad B)
umgeht das nur, weil es Check24s eigenes JS im echten Browser laufen lässt —
kein Vertragsbruch der Verschlüsselung, aber ein aufwändigerer/fragilerer Weg
als TUIs offenes JSON-API. Siehe Risiko-Abschnitt im Implementierungsplan.
