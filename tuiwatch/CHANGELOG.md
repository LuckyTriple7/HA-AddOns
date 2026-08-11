# Changelog

## [0.90.1] - 2026-08-11

### Added
- **Fragebogen-Editor in der Oberfläche.** Ein **Rechtsklick auf „🗺️ TripPilot"**
  öffnet einen Editor für den Fragebogen — kein Umweg mehr über Dateimanager,
  Samba oder Studio Code Server. Bearbeitet wird dieselbe Datei
  (`/config/trippilot/questions.json`); beide Wege bleiben also nutzbar.
  Möglich sind: Fragen anlegen, umsortieren und löschen, Titel, Prompt-Label,
  Feldname und Typ ändern, Antwortmöglichkeiten pflegen (inkl. „exklusiv" bei
  Mehrfachauswahl), Pflichtfrage setzen, die Bedingung `show_if` als JSON
  bearbeiten, den Tagesausflug-Wert auswählen und den `semantics`-Block
  bearbeiten. „Auslieferungsstand laden" holt die mitgelieferten Fragen in den
  Editor, gespeichert wird erst auf Knopfdruck.
- **Umbenennen zieht alle Nennungen mit.** Ein Antwortwert steht oft nicht nur
  in `options`, sondern auch in `exclusive`, in `show_if` anderer Fragen, im
  `semantics`-Block und bei `daytrip_value`. Der Editor ändert beim Umbenennen
  oder Löschen einer Option alle diese Stellen mit — genau der Handgriff, den
  zu vergessen in 0.90.0 vier Kopplungen stillgelegt hätte. Werte, die in
  mehreren Fragen gleich heißen (z. B. „Keine Präferenz"), bleiben dabei
  bewusst unangetastet, weil sich nicht entscheiden lässt, welche gemeint war.

### Changed
- **Gespeichert wird nur ein fehlerfreier Fragebogen.** Der Editor schickt das
  Dokument zur Prüfung an das Add-on; bei Problemen wird nichts geschrieben und
  die Fehler stehen mit Fragen-Nummer im Editor. Eine über die Oberfläche
  erzeugte Datei kann den Wizard also nie auf die Auslieferungsversion
  zurückwerfen. Geschrieben wird über eine Temp-Datei plus `os.replace`, damit
  ein Abbruch keine halbe Datei hinterlässt.
- Eine fehlerhafte eigene `questions.json` zeigt der Editor **so, wie sie auf
  der Platte liegt** — nur wenn sie nicht einmal gültiges JSON ist, tritt der
  Auslieferungsstand an ihre Stelle (mit Hinweis). Sonst würde man im Editor
  etwas anderes reparieren als das, was gespeichert ist.
- Nach dem Speichern lädt der Wizard den Fragebogen beim nächsten Öffnen neu —
  ohne Seiten-Reload und ohne Add-on-Neustart.

## [0.90.0] - 2026-08-11

### Added
- **Überarbeiteter TripPilot-Fragebogen.** 31 statt 29 Fragen, durchgehend
  ausformulierte Antworten mit Symbolen. Neu: **Reisetempo** (wie voll darf
  der Tag sein) und **Transferdauer** (wie lange vom Flughafen zum Hotel).
  Deutlich mehr Auswahl bei Hotelwünschen, Aktivitäten und besonders bei
  „Was möchtest du vermeiden?" (u. a. Luftfeuchtigkeit, Stechmücken,
  Seegras, Baustellen, sehr touristische Orte). Feinere Abstufungen bei
  Temperatur, Regen und Budget.
- **`semantics`-Block in der Fragen-JSON.** Einige Antwortwerte lösen nicht
  nur Prompt-Text aus, sondern Logik — Tagesausflug-Modus, die
  Eigenanreise-Klausel, der Veranstalter-Hinweis bei Pauschalreisen und die
  Signale der Reise-DNA. Bisher standen diese Werte fest in `ai_routes.py`;
  jetzt stehen sie in derselben Datei wie die Fragen. Damit lassen sich
  Antworten frei umbenennen, ohne dass Funktionen still ausfallen. Fehlt der
  Block, gelten weiter die eingebauten Standardwerte.

### Fixed
- **Validierung prüft jetzt auch Antwortwerte.** Ein Wert in `show_if`, in
  `semantics` oder bei `daytrip_value`, den es als Option gar nicht gibt,
  galt bisher als gültig — die betroffene Frage wäre dann stumm nie wieder
  erschienen und der Tagesausflug-Modus nicht auswählbar gewesen. Solche
  Abweichungen sind jetzt ein gemeldeter Fehler mit Angabe des Werts. Genau
  diese Klasse Fehler entsteht beim Umbenennen von Optionen.

### Changed
- **Reise-DNA wertet mehr Fragen aus.** „Aktiv" und „Entspannung" beziehen
  jetzt auch das neue Reisetempo ein, „Kulinarik" die Hotelwünsche, „Kultur"
  die Sehenswürdigkeiten-Antworten. Die Zählweise bleibt: 15 % Sockel, je
  zutreffender Frage +35 %, mehrere Treffer in derselben Frage zählen einmal.

## [0.89.12] - 2026-08-11

### Changed
- **TripPilot-Fragen stehen jetzt in einer editierbaren JSON-Datei.** Bis
  hierher waren sie an zwei Stellen fest im Code hinterlegt — im Frontend
  (`ADV_STEPS`) für Anzeige und Sichtbarkeit, im Backend
  (`_ADVISOR_FIELDS`/`_ADVISOR_LABELS`) für den KI-Prompt. Beides kommt nun
  aus **einer** Datei: `/config/trippilot/questions.json`, im Dateimanager
  oder per Samba direkt neben `/config/backups` bearbeitbar. Änderungen
  greifen beim nächsten Öffnen des Fragebogens, ohne Add-on-Neustart.
  Bearbeitbar sind Fragetext, Reihenfolge, Antwortmöglichkeiten, Frage-Art
  (Mehrfachauswahl/Einzelauswahl/Freitext) und die Bedingung, wann eine
  Frage überhaupt erscheint. Weil auch das Backend diese Datei liest, landet
  eine neu ergänzte Frage wirklich im KI-Prompt statt beim Absenden still
  verworfen zu werden.
- **Bedingungen ohne Code.** Die bisherigen JavaScript-Ausdrücke hinter
  `showIf` sind durch ein deklaratives `show_if` ersetzt — `contains`,
  `contains_any`, `equals`, `in`, `answered`, verknüpfbar mit `all`, `any`
  und `not`. Der ausgelieferte Fragebogen verhält sich unverändert.
- **Updatesicher.** Eine einmal angelegte `questions.json` wird von
  Add-on-Updates nie überschrieben. Der jeweils aktuelle Auslieferungsstand
  liegt zum Vergleichen als `questions.default.json` daneben und wird bei
  jedem Start erneuert, dazu eine `README.md` mit dem vollständigen Schema.
- **Kaputte Datei legt nichts lahm.** Unlesbares JSON oder ein Schemafehler
  führen nicht zum leeren Fragebogen: es gelten weiter die mitgelieferten
  Fragen, und der erste Fehler steht mit Dateipfad direkt auf Schritt 1 des
  Wizards sowie im Add-on-Log.
- Neuer Endpunkt `GET /api/trippilot/questions` (liefert Fragen, Quelle und
  etwaige Fehler). Ein GUI-Editor dafür ist noch nicht enthalten.

## [0.89.11] - 2026-08-11

### Added
- **Rechtsklick aufs Logo → „Nächste Läufe".** Zeigt für jede
  Hintergrund-Aufgabe (Preis-Checks, Suchabos, Preiskalender,
  Preisbarometer, Aktionscodes, API-Selbsttest, Backup, wöchentliche
  Zusammenfassung), wann sie das nächste Mal ansteht — als Restzeit plus
  Uhrzeit, fällige zuerst, abgeschaltete als solche markiert. Dazu je
  Zeile eine Notiz mit dem Warum (z. B. „12 aktiv · als Nächstes: Hotel
  Riu", „3 von 8 Messreihen heute offen", „wöchentlich, Montag"). Alle
  Zeiten sind Frühestens-Angaben: der Poller startet Fälliges erst beim
  nächsten Aufwachen, der Kopf der Ansicht nennt seinen Takt. Neuer
  Endpunkt `GET /api/schedule`; der Doppelklick (Konsole) bleibt
  unverändert.

## [0.89.10] - 2026-08-11

### Fixed
- **„Meine Reisen" → „📅 Als Kalender (.ics)" war kaum lesbar.** Der Link
  war der einzige `.hc-foot` als `<a>` und bekam damit die
  Browser-Standardfarbe (Blau, unterstrichen) — auf dunklem Grund
  schlecht lesbar. Steht jetzt wie die übrigen Einträge in Textfarbe,
  Unterstreichung und Akzentfarbe erst beim Hover.

## [0.89.9] - 2026-08-11

### Added
- **Logo signalisiert Hintergrund-Aktivität.** Läuft im Hintergrund etwas
  (Preis-Checks, Suchabos, Preiskalender, Preisbarometer, Aktionscodes,
  Selbsttest, Backup, wöchentliche Zusammenfassung), färbt sich der
  Schriftzug „TUIWatch" samt Flieger bernsteinfarben, der Flieger pulst
  dezent. Der Tooltip nennt die laufenden Aufgaben im Klartext
  („Läuft gerade: Preis-Checks (10), Preiskalender"), sonst steht dort
  wie bisher der Konsolen-Hinweis. `prefers-reduced-motion` schaltet die
  Animation ab, die Farbe bleibt. Die Labels kommen über `/api/offers`
  mit (kein zweiter Poll-Timer), Aktualisierung damit alle 5 Sekunden.

## [0.89.8] - 2026-08-11

### Added
- **Pause zwischen Hintergrund-Abrufen (`poll_gap`, Standard 10 s).** Der
  Poller arbeitet alle fälligen Angebote seriell in einem Block ab; bei
  vielen Angeboten entstand so ein Burst von Abrufen innerhalb weniger
  Sekunden. Zwischen zwei Angeboten (und zwischen zwei Suchabos) liegt
  jetzt eine Pause von `poll_gap` Sekunden plus 0–5 s Zufall, damit die
  Abrufe kein exaktes Taktmuster ergeben. Die Pause greift nur im
  Hintergrund — „Jetzt prüfen" aus der UI bleibt unverändert sofortig.
  `poll_gap: 0` schaltet sie ab.

## [0.89.7] - 2026-08-11

### Changed
- **Trip Pilot, Reiseart „Pauschalreise (TUI)" → „Pauschalreise"**
  entschärft. KI-Prompt verlangte bislang eine strikte Einzelprüfung, ob
  TUI das Ziel nachweislich im Katalog führt — daran scheiterten
  Websuchen (z. B. Perplexity) mangels belastbarer Treffer. Prompt
  plausibilisiert jetzt grob über gängige Veranstalter (TUI, DER
  Touristik, FTI) statt eine einzelne Quelle hart zu verifizieren.

## [0.89.6] - 2026-08-10

### Added
- **STR-Flugdetails: Link „Live-Position auf planefinder.net"** im
  Detail-Popup — direkt neben den adsbdb-Infos, unabhängig von deren
  Ladezustand nutzbar. (Live-Lookup über OpenSky wurde geprüft: kein
  `callsign`-Filter im API, TUIfly sendet als Charter-Airline zudem
  Rotations-Callsigns ohne erkennbaren Bezug zur Flugnummer — für einen
  Fahrplan-Browser nicht sinnvoll konstruierbar, siehe Konsolen-Diskussion.)

## [0.89.5] - 2026-08-10

### Fixed
- **STR-Flugplan-Modal komplett kaputt** — beim Einfügen des Blocks in
  `index.html` waren HTML-Attribut-Anführungszeichen (`id="…"`, `class="…"`,
  `viewBox="…"`) durch typografische Zeichen (`"…"`) ersetzt worden. Browser
  erkannten die Attribute nicht mehr, `getElementById()` lieferte `null`,
  app.js crashte beim Start und SVG-Icons rendern kaputt. Zurück auf gerade
  Anführungszeichen.

### Added
- **Regressionstest `test_template_quotes.py`** — prüft alle `templates/*.html`
  auf typografische Anführungszeichen an Attribut-Delimiter-Position, damit
  dieser Fehler künftig vor dem Commit auffliegt statt live.

## [0.89.4] - 2026-08-10

### Added
- **STR-Flugplan: Flugdetails per Klick** — jede Zeile ist jetzt anklickbar
  und zeigt Airline, Callsign sowie die planmäßige Standardstrecke (Start-/
  Zielflughafen mit Ort). Nutzt das offene Community-API adsbdb.com (Callsign
  aus Fluggesellschaftscode + Flugnummer), server-seitig geproxied und 12h
  gecacht. Reine Zusatzinfo — nicht jeder Callsign hat dort hinterlegte Daten.

## [0.89.3] - 2026-08-10

### Added
- **STR-Flugplan: Zeitraum-Filter** (von/bis, Monatsauswahl) — grenzt die
  Suche auf Verbindungen ein, deren Saisonzeitraum das gewählte Fenster
  überschneidet.

### Changed
- **STR-Flugplan-Suchfeld schmaler**, Zeitraum-Filter passt in dieselbe Zeile.
- **Zeitraum-Spalte zeigt nur noch Monat + Jahr** (z. B. „Okt 2026–Mär 2027“
  statt „31.10.2026–27.03.2027“) — Tagesgenauigkeit war für die Saisonspanne
  einer Fahrplanzeile keine nützliche Information.

## [0.89.2] - 2026-08-10

### Fixed
- **STR-Flugplan-Suche fand scheinbar nichts** (z. B. Suche nach „LPA“):
  `Via` (Zwischenstopp-Flughafen) liefert das API entgegen der ursprünglichen
  Annahme kein Code-String, sondern ein volles Airport-Objekt — ungeprüft ans
  Frontend durchgereicht crashte `esc()` dort (`(s||"").replace is not a
  function`), das Rendering brach vor dem Anzeigen ab. `str_flights_client.py`
  extrahiert jetzt nur `Via.Code`; alle übrigen Felder zusätzlich hart auf
  `str()` abgesichert. `esc()` selbst stringt jetzt defensiv (`String(s||'')`
  statt `(s||'')`) gegen künftige Typüberraschungen aus JSON-APIs.

## [0.89.1] - 2026-08-10

### Fixed
- **Add-on startete nicht** (`ModuleNotFoundError: No module named 'str_flights_routes'`):
  Dockerfile kopierte die neuen Module aus 0.89.0 nicht ins Image (Fix kam erst
  nach dem Image-Build). Reiner Dockerfile-Commit hatte zudem den Image-Build-
  Workflow gar nicht getriggert (Pfad-Filter reagiert nur auf `config.yaml`) —
  dieser Versionsbump erzwingt den Rebuild.
- **Fehlende Übersetzung**: `enable_str_flights` zeigte im Add-on-Konfigurations-
  formular nur den rohen Options-Key statt Name/Beschreibung (DE+EN nachgetragen).

## [0.89.0] - 2026-08-10

### Added
- **Flugplan ab Stuttgart Airport (STR)** (neuer ✈️-Knopf in der Kopfzeile,
  Opt-in `enable_str_flights`): eigenständige Suche nach Linienflug-
  Verbindungen (Abflug/Ankunft, Fluggesellschaft, Wochentage, Zeiten,
  Saisonzeitraum) über Zielflughafen oder Land. Nutzt das offene JSON-API des
  Flughafen-Betreibers (`fsg-datahub.azure-api.net`), keine Anmeldung nötig,
  komplett unabhängig von TUI-/Check24-Angeboten. Details: SCRAPING_STR.md.

## [0.88.0] - 2026-08-07

### Added
- **Knopf „Klima" am Angebot** (links neben „Reiseführer"): öffnet die Klimatabelle
  der Region direkt aus der Liste, ohne den Umweg über Suche oder Kopfzeile. Wie
  beim Reiseführer leuchtet der Knopf **grün**, wenn die Tabelle zu diesem Ziel
  bereits gespeichert ist — dann kostet das Öffnen keinen KI-Aufruf.

### Changed
- **„Prüfen" ist jetzt ein Lupensymbol** und steht rechts bei den übrigen
  Symbolknöpfen. Die Zeile war mit den beschrifteten Knöpfen bereits am Anschlag;
  so bleibt Platz für „Klima".

## [0.87.4] - 2026-08-07

### Fixed
- **Klimatabelle im Markdown-Export: „21 °C" brach in der schmalen Spalte „Tag"
  auf zwei Zeilen um** und machte die Zeile doppelt hoch. Zwischen Zahl und
  Einheit steht jetzt ein geschütztes Leerzeichen, damit kein Renderer dort
  trennt — gilt für °C, Sonnenstunden und alle weiteren Werte.

## [0.87.3] - 2026-08-07

### Security
- **CodeQL #194 (`js/incomplete-sanitization`)**: Beim Markdown-Export maskierte
  die Klimatabelle nur das `|`, nicht den Backslash davor. Ein Zellinhalt wie
  `C:\Temp \| x` brach die Tabelle deshalb wieder auf. Escaping läuft jetzt in
  der einzig richtigen Reihenfolge — erst Backslash, dann `|` — und
  Zeilenumbrüche in einer Zelle fliegen raus.
- **Fremde Header landen nicht mehr ungeprüft im Log und in der Datenbank**:
  `get_client_ip` gibt nur noch ein geprüftes IP-Literal oder `remote_addr`
  zurück. Vorher konnte im Rückfall beliebiger Text aus `X-Forwarded-For`
  durchrutschen (Log-Injection über untergeschobene Zeilenumbrüche, außerdem
  Unsinn in der Kommentar-Ansicht). Die Diagnose-Warnung zu fehlenden
  Proxy-Headern schickt ihre Werte zusätzlich durch `log_safe()`
  (Steuerzeichen raus, gekappt).

## [0.87.2] - 2026-08-07

### Fixed
- **Reiseziel-Namen in den Listen von Klimatabelle und Reiseführer** standen im
  Browser-Blau samt Unterstreichung — im dunklen Design kaum lesbar, bereits
  geöffnete Ziele zusätzlich violett („besucht"). Sie sind Bedienelemente, keine
  Verweise nach draußen, und stehen jetzt in normaler Textfarbe ohne
  Unterstreichung; beim Überfahren färben sie sich in der Akzentfarbe.

## [0.87.1] - 2026-08-07

### Fixed
- **Adressen im Markdown-Export sind jetzt klickbare Links.** Bisher stand die
  nackte Adresse im Text (`(https://www.marcopolo.de/…)`) und war in keiner
  Notiz-App anklickbar. Sie wird an Ort und Stelle zu `[marcopolo.de](…)` — der
  Satz bleibt heil (ans Zeilenende verschoben blieben Reste wie „Details:" ohne
  Bezug stehen), die Quelle bleibt nachvollziehbar. Bereits fertige
  Markdown-Links bleiben unangetastet, und ein `|` in einer Adresse sprengt die
  Klimatabelle nicht mehr auf.

## [0.87.0] - 2026-08-07

### Added
- **📋 Markdown** in Reiseführer und Klimatabelle: legt den Inhalt als sauberes
  Markdown in die Zwischenablage, zum Einfügen in eine Notiz-/Wissenssammlung
  (z. B. die Bibliothek von MyPage). Gebaut wird es aus den gespeicherten Daten
  statt aus der Bildschirmdarstellung — kopierter Seitentext bringt sonst
  Aufzählungszeichen, Tabellenrahmen und Symbole als Fließtext mit. Abschnitte
  werden zu `##`, Punkte zu `- **Label:** Text`, Monatswerte zu einer
  Markdown-Tabelle (★ für die besten Reisemonate, Hinweis-Spalte nur wenn es
  welche gibt); beim Reiseführer hängt die Klimatabelle mit dran. Quellen-Marker
  der KI (`[3]`) fallen weg, das ⏱ für kurzlebige Angaben wird als
  „(kann sich kurzfristig ändern)" ausgeschrieben.
  Kopiert wird über `navigator.clipboard` mit textarea-Rückfallebene — im
  Ingress über http fehlt die Clipboard-API sonst.

## [0.86.0] - 2026-08-07

### Added
- **Kommentare je Link an-/abschaltbar** (Standard an): Haken **„Kommentare"** im
  Teilen-Dialog und ein Schalter oben im Kommentar-Fenster. Aus bedeutet „nichts
  Neues": das Formular verschwindet von der öffentlichen Seite, **bereits
  geschriebene Kommentare bleiben sichtbar**. Sind Kommentare aus und noch keine
  vorhanden, fehlt der Abschnitt dort ganz.

### Fixed
- **Bei Kommentaren stand die interne Adresse statt der echten Client-IP**
  (z. B. 172.30.32.1, die Docker-Bridge). Zwei Ursachen: `get_client_ip` sah nur
  `CF-Connecting-IP` und sonst `remote_addr`, und waitress verwirft
  `X-Forwarded-For`, solange kein `trusted_proxy` gesetzt ist.
  `get_client_ip` prüft jetzt der Reihe nach `CF-Connecting-IP`,
  `True-Client-IP`, `X-Real-IP` und dann den ersten öffentlichen Eintrag der
  `X-Forwarded-For`-Kette; private/interne Adressen werden dabei übersprungen,
  eine LAN-Adresse bleibt aber stehen, wenn es nichts Besseres gibt.
  **Damit das greift, muss der Reverse Proxy `X-Real-IP` setzen** (nginx/NPM:
  `proxy_set_header X-Real-IP $remote_addr;`) oder Cloudflare davorstehen —
  `X-Forwarded-For` allein reicht wegen waitress nicht. Fehlt beides, sagt eine
  Warnung im Log genau das.

## [0.85.0] - 2026-08-07

### Added
- **Benachrichtigung bei neuen Kommentaren** über Home Assistant und Telegram —
  mit Name, Text (auf 300 Zeichen gekürzt) und **Absender-IP**. Abschaltbar über
  die neue Option **„Benachrichtigung bei neuen Kommentaren"** (Standard an).
- **Absender-IP je Kommentar** (`share_comments.ip`), sichtbar nur in der
  Kommentar-Verwaltung des Besitzers — auf der öffentlichen Seite steht sie
  nicht (durch Test abgesichert). Hinter Cloudflare wird `CF-Connecting-IP`
  ausgewertet, sonst die Adresse aus dem Proxy-Header, es steht also die echte
  Client-IP da und nicht die des Reverse-Proxys.

## [0.84.0] - 2026-08-07

### Added
- **Kommentare auf geteilten Seiten.** Unter den Angeboten steht ein Kommentarfeld
  (Name optional, max. 500 Zeichen); die Empfänger können damit direkt antworten —
  ohne Login, ohne App und ohne JavaScript (normales Formular, POST → Redirect).
  In **🔗 Geteilte Links** gibt es je Link den Knopf **„💬 Kommentare"**, der
  **grün leuchtet**, solange etwas Ungelesenes da ist; das Öffnen markiert die
  Kommentare als gelesen. Dort lassen sie sich auch **bearbeiten und löschen**,
  beides wirkt sofort auf die öffentliche Seite. Widerrufen oder Ablaufen eines
  Links räumt seine Kommentare mit weg.
  Weil die Seite öffentlich beschreibbar ist, gelten harte Grenzen: 500 Zeichen je
  Kommentar, 40 für den Namen, 200 Kommentare je Link, 5 je IP und 10 Minuten;
  gespeichert wird reiner Text, die Ausgabe läuft über Autoescape (in Tests
  gegengeprüft). Die CSP der öffentlichen Seite erlaubt dafür jetzt
  `form-action 'self'` statt `'none'` — Formulare gehen weiterhin nur an die
  eigene App.
  Neue Endpunkte: `POST /s/<token>/comment` (öffentlich),
  `GET|PATCH|DELETE /api/shares/<token>/comments[/<id>]` (geschützt).

## [0.83.3] - 2026-08-07

### Changed
- **Schalter „Archiv" zeigt jetzt nur noch die archivierten Angebote** — wie
  „Preisverlauf" für die Verlaufs-Hotels, statt das Archiv zusätzlich unter die
  aktive Liste zu hängen. Beide Schalter schließen sich gegenseitig aus (der eine
  hakt den anderen ab); die Tag-Pillen zeigen entsprechend nur die Tags der
  gerade sichtbaren Angebote.

## [0.83.2] - 2026-08-07

### Changed
- **Auto-Tag beim Tracken vergibt nur noch die Region** („Mauritius",
  „Gran Canaria") statt „Ort, Region" („Palmar, Mauritius"). Der Ort ist als
  Filter zu speziell — praktisch bekam jedes Hotel seinen eigenen Tag. Die
  Such-API liefert die Region dafür getrennt mit; in der Anzeige steht weiter
  „Ort, Region". Bestehende Tags bleiben, wie sie sind.
- **Sammelaktionen-Leiste zweizeilig**: oben die Anzahl und rechts „Auswahl
  aufheben", darunter die Aktionsknöpfe. Vorher lief alles in einer
  umbrechenden Zeile, „Auswahl aufheben" landete je nach Fensterbreite
  irgendwo zwischen den Aktionen.

### Fixed
- **Teilen-Dialog wurde auf flachen Fenstern abgeschnitten** (Laptop im
  Querformat, ~500 px Höhe): die Angebotsliste hatte feste 230 px, zusammen mit
  Titel, Notiz, Optionen und Knopf passte das nicht mehr in die 88 vh des
  Fensters. Die Liste bekommt jetzt einen Anteil der Fensterhöhe
  (`clamp(110px, 30vh, 240px)`), unter 760 px Fensterhöhe darf das Fenster
  96 vh nutzen. Geprüft mit 10 Angeboten bei 1142 × 506 px: nichts
  abgeschnitten, die Liste scrollt für sich.
- **Spalte „Ort · Preis" im Teilen-Dialog war zu schmal** (210 → 270 px), lange
  Ziele wie „Ziyaaraifushi, Malediven: Nord Male Atoll" brachen mit „…" ab.

## [0.83.1] - 2026-08-07

### Changed
- **Teilen-Dialog zeigt die „Für andere"-Liste in einer eigenen Spalte** (Symbol +
  Name, leer bei eigenen Angeboten) — beim Teilen ist meist genau eine Liste
  gemeint, in der bisherigen Aufzählung sah aber jedes Angebot gleich aus. Dazu
  eine Kopfzeile (Angebot · Liste · Ort · Preis) und feste Spaltenbreiten, damit
  die Zeilen fluchten. Das Fenster ist von 900 auf 1150 px verbreitert; auf
  schmalen Bildschirmen (< 700 px) brechen die Spalten wie bisher untereinander.

## [0.83.0] - 2026-08-07

### Added
- **Eigenes Symbol je „Für andere"-Liste.** Klick auf das Symbol in der
  Listen-Überschrift öffnet einen Emoji-Picker (50 Vorschläge rund ums Reisen
  plus Freitextfeld für jedes andere Zeichen, auch zusammengesetzte Emojis wie
  👨‍👩‍👧 oder ein ★). Beim Anlegen einer Liste lässt sich das Symbol gleich
  mitwählen; später einsortierte Angebote erben es, eine Änderung gilt für alle
  Angebote der Liste. Auch der 👥-Knopf auf der Karte zeigt das Symbol der Liste,
  in der das Angebot steckt.
  Das Symbol steht wie der Name am Angebot (`offers.foreign_icon`, leer = 👥) und
  wandert damit durch Backup/Restore. Neuer Endpunkt:
  `POST /api/foreign-lists/icon`; `GET /api/foreign-lists` liefert das Symbol mit.

## [0.82.2] - 2026-08-07

### Changed
- **Listen-Überschrift zeigt nur noch Name und Anzahl** — der Zusatz
  „— keine Benachrichtigungen" ist raus, er stand über jeder Liste im Weg. Die
  Info steht weiter im Tooltip der Überschrift.

## [0.82.1] - 2026-08-07

### Fixed
- **Listen ließen sich nicht umbenennen** („Uncaught SyntaxError: missing ) after
  argument list"). Für die ✎/✖-Knöpfe wurde eine zweite Hilfsfunktion `jsArg`
  angelegt — den Namen gab es in app.js aber schon, mit anderer Bedeutung (escapt
  für einfache Anführungszeichen, setzt selbst keine). Die spätere Deklaration
  gewinnt, also stand im Attribut `renameForeignList(Für andere)` statt
  `renameForeignList("Für andere")`. Listennamen sind freier Text und stehen
  jetzt gar nicht mehr in einem Inline-Script, sondern in `data-list`; geklickt
  wird über Event-Delegation. Damit sind auch Namen mit Anführungszeichen,
  Klammern oder Backslash unproblematisch (im Browser gegengeprüft).

## [0.82.0] - 2026-08-07

### Added
- **Mehrere „Für andere"-Listen mit frei wählbaren Namen.** Bisher gab es genau
  einen Block „👥 Für andere"; jetzt legt das 👥-Symbol auf der Karte (bzw.
  „👥 Für andere" in der Auswahlleiste) eine Auswahl offen: bestehende Liste
  anklicken oder neuen Namen eintippen („Oma und Opa", „Kollegen", …). Jede
  Liste bekommt einen eigenen Block am Listenende, alphabetisch sortiert; in der
  Überschrift benennt **✎** die Liste um (gleicher Name wie eine andere = beide
  werden zusammengeführt) und **✖** löst sie auf, wobei die Angebote zurück in
  die normale Liste wandern. Verhalten sonst unverändert: eingeklappte Karten,
  Glocken beim Einsortieren stumm und beim Herausnehmen bewusst nicht wieder an.
  Der Listenname steht am Angebot selbst (`offers.foreign_list`) und wandert
  daher ohne Zusatztabelle durch Backup/Restore; Bestandsangebote landen bei der
  Migration in der Liste „Für andere". Neue Endpunkte: `GET /api/foreign-lists`,
  `POST /api/foreign-lists/rename`, `DELETE /api/foreign-lists/<name>`.

## [0.81.0] - 2026-08-06

### Changed
- **Sterne, Weiterempfehlung und Höchstpreis gehen jetzt in die Such-Anfrage**
  statt erst hinterher aussortiert zu werden. Die Such-API sortiert nach Preis
  aufsteigend — in den ersten 50 Treffern stehen deshalb fast nur einfache
  Hotels, und ein 4-Sterne-Filter ließ davon eine Handvoll übrig. Beispiel
  (Kanaren, All Inclusive, ab STR, 9 Nächte, Transfer inklusive):
  272 Treffer → 206 (ab 4 Sterne) → 135 (+ 80 % Weiterempfehlung) — genau die
  Zahl, die tui.com für dieselben Filter anzeigt. Mit Preisdeckel 1.500 €
  bleiben 8 übrig, alle darunter.
  Die bisherigen Nachfilter bleiben als Netz erhalten.
  Damit berücksichtigt die Suchmaske alle Optionen bereits serverseitig:
  Nächte, Reisende, Airlines, Veranstalter, Transfer, Direktflug, nur
  Erwachsene, Verpflegung, Lage — und nun auch Sterne, Weiterempfehlung und
  Höchstpreis.

### Fixed
- **„Mehr laden" in der Hotelsuche brachte kaum neue Treffer** — als Startpunkt
  der nächsten Seite wurde die Anzahl der **angezeigten** Treffer geschickt.
  Sind Nachfilter aktiv (Sterne, Weiterempfehlung, Höchstpreis), sind das viel
  weniger als die 50 tatsächlich abgeholten: die nächste Seite holte fast
  dieselben Hotels erneut, es kam einer dazu, danach nichts mehr. Der Server
  meldet jetzt mit, wie viele Angebote er wirklich durchsucht hat; danach
  richtet sich der Seitenanfang. Beispiel (Kanaren, ab 4 Sterne, ab 80 %
  Weiterempfehlung): 8 → 21 → 43 → 76 Treffer statt 8 → 9 → Stillstand.
- **„Nachladen fehlgeschlagen" war irreführend**, wenn nur der eigene
  3-Sekunden-Abstand zwischen zwei Suchen gegriffen hat (HTTP 429) — jetzt
  steht dort, dass man kurz warten und erneut tippen soll.
- Die Kopfzeile der Trefferliste zeigt jetzt „X Treffer · Y von Z Angeboten
  durchsucht", damit der Unterschied zwischen gefundenen und gefilterten
  Treffern sichtbar ist.

## [0.80.1] - 2026-08-06

### Fixed
- **Klima- und Reiseführer-Fenster hingen dauerhaft bei „Lade…"** — wurde das
  Fenster bei offener Prompt-Vorschau (Option „KI-Prompt vor dem Senden
  anzeigen") geschlossen, blieb das Versprechen hinter der Vorschau für immer
  offen. Damit stand die interne „läuft gerade"-Sperre bis zum Neuladen der
  Seite auf true und jedes weitere Öffnen zeigte nur den Ladebalken — ohne
  Fehlermeldung in der Konsole. Schließen bricht die Vorschau jetzt sauber ab.
- Läuft tatsächlich schon ein Abruf (z. B. das Vorabladen der Klimatabelle nach
  einer Suche), steht das jetzt im Fenster, statt den Ladebalken stumm stehen
  zu lassen.

## [0.80.0] - 2026-08-06

### Added
- **Angebote als „für andere" markieren (👥)** — für Reisen, die nicht für einen
  selbst sind. Sie rutschen unter eine eigene Überschrift ans Listenende und
  werden dort **eingeklappt** gezeigt (Titel, Tags, Ort, Reisedaten, Preis);
  ▾ klappt die volle Karte auf, der Zustand überlebt das Neuladen.
  Beim Markieren werden **Benachrichtigungen und Kalender-Meldungen
  stummgeschaltet** — einschalten geht jederzeit über die Glocken, das
  Zurücknehmen der Markierung tut es bewusst nicht von selbst.
  Markieren über das 👥-Symbol auf der Karte oder „👥 Für andere" in der
  Auswahlleiste für mehrere auf einmal.
  Preisprüfung, Verlauf, Kalender, Tags, Wunschpreis, Überblick, HA-Sensoren und
  die Teilen-Funktion bleiben unverändert.

## [0.79.1] - 2026-08-06

### Fixed
- **Falscher Reiseführer/falsche Klimatabelle bei mehreren Zielen im selben
  Land** — die Region eines Angebots wurde bevorzugt aus `regionGiataIds` der
  Angebots-URL gelesen. Dort steht aber die Region, in der *gesucht* wurde: zwei
  Malediven-Hotels aus einer Landessuche trugen beide „Malediven" (100020) und
  teilten sich dadurch Reiseführer und Klimatabelle, obwohl sie auf
  verschiedenen Atollen liegen. Beim zweiten Angebot öffnete sich der
  Reiseführer des ersten. Aufgelöst wird jetzt zuerst über die Breadcrumb-API
  (Addu Atoll 1139 vs. Nord Male Atoll 1151), die URL-Region ist nur noch der
  Notnagel.
  - **Hinweis:** Bereits erzeugte Reiseführer/Klimatabellen hängen weiter an der
    gröberen Region. Sie werden für die jetzt korrekt aufgelöste Insel neu
    erstellt; die alten Einträge lassen sich in der Reiseführer- bzw.
    Klima-Übersicht löschen.

## [0.79.0] - 2026-08-06

### Added
- **Hotelbeschreibung (PDF) im öffentlichen Link** — je Angebot verlinkt, wie
  in der Oberfläche. Verlinkt wird wie beim Angebots-Link nur, was per https
  auf tui.com zeigt.

### Fixed
- **Klima/Reiseführer aus dem Teilen-Dialog wurden nicht erstellt** — bei
  aktiver Option „KI-Prompt vor dem Senden anzeigen" antworteten die Endpunkte
  nur mit der Prompt-Vorschau statt zu erzeugen; das Fortschrittsfenster war
  kurz zu sehen und danach stand sofort der Link da. Der Aufruf schickt jetzt
  `_prompt_confirmed` — die Rückfrage im Dialog ist die Bestätigung, ein
  zweites Vorschaufenster wäre doppelt gemoppelt.
- Fehlgeschlagene Erzeugungen werden jetzt im Dialog benannt (vorher nur eine
  leicht zu übersehende Kurzmeldung), bevor der Link gespeichert wird.
- **Liste der geteilten Links zu schmal** — die Knöpfe „Kopieren / Bearbeiten /
  +30 T / Widerrufen" brachen in eine zweite Reihe um und die Kopfzeile
  „Gültig bis" auf zwei Zeilen. Das Fenster ist jetzt breiter, die
  Aktionsspalte bleibt einzeilig, auf schmalen Displays scrollt die Tabelle
  waagerecht.

## [0.78.0] - 2026-08-06

### Added
- **Öffentliche Links lassen sich bearbeiten** — „Bearbeiten" in der Liste
  „🔗 Geteilte Links" öffnet die Zusammenstellung erneut: Angebote hinzufügen
  oder entfernen, Titel, Notiz, Extras und Gültigkeit ändern. **Der Link bleibt
  derselbe**, Aufrufzähler und Erstelldatum ebenfalls — bisher musste für jede
  Änderung ein neuer Link erzeugt und verteilt werden.
- Der Teilen-Dialog zeigt jetzt alle Angebote zum An- und Abhaken (vorher nur
  die vorher markierten), damit sich beim Bearbeiten überhaupt etwas ergänzen
  lässt.
- **Rückfrage bei fehlendem Klima/Reiseführer** — sind sie zum Reiseziel noch
  nicht gespeichert, fragt der Dialog vor dem Speichern, ob sie per KI erstellt
  werden sollen, und zeigt den Fortschritt je Ziel. Wer ablehnt, bekommt den
  Link ohne diese Abschnitte; ohne KI-Key kommt nur ein Hinweis. Vorher entstand
  stillschweigend ein Link, in dem der angehakte Abschnitt schlicht fehlte.

## [0.77.0] - 2026-08-06

### Added
- **Öffentliche Links zeigen Preis und Verfügbarkeit live** — beide werden bei
  jedem Aufruf frisch aus der Datenbank gelesen, samt Zeitpunkt der letzten
  Prüfung und Badge „verfügbar" / „nicht mehr verfügbar". Gelesen wird nur zu
  den geteilten Angebots-IDs; die Seite fragt selbst nichts bei TUI ab.
  Auswahl, Beschreibung, Klima, Reiseführer und Reiseberater-Text bleiben
  weiterhin der Stand vom Erzeugen.
- **Links je Angebot** auf der öffentlichen Seite: TUI-Angebotsseite (nur
  `*.tui.com` wird verlinkt) und HolidayCheck-Bewertungen über dieselbe
  Google-Seitensuche wie in der Oberfläche.
- Wird ein geteiltes Angebot gelöscht, zeigt der Link weiter den letzten
  bekannten Stand statt einer Lücke.

## [0.76.0] - 2026-08-06

### Added
- **Öffentliche Angebots-Links (🔗 Teilen)** — ausgewählte Angebote lassen sich
  als Seite zum reinen Anschauen weitergeben, ohne Login, wie beim Reisebüro.
  Enthält auf Wunsch die gespeicherte Klimatabelle, den Reiseführer, ein
  Reiseberater-Ergebnis und den Preisverlauf. Verwaltung (Aufrufe, Gültigkeit,
  Widerruf) über „🔗 Geteilte Links" im Footer.
  - Läuft auf einem **eigenen Port** (Standard 17796), damit im Reverse-Proxy
    nur die öffentliche Seite freigegeben werden kann — Port 17794 mit Login,
    API und Ingress bleibt unangetastet. Ohne `enable_public_share` wird der
    Port gar nicht erst gebunden.
  - Der Inhalt wird beim Erzeugen als Schnappschuss eingefroren; die öffentliche
    Seite liest nie die Live-Tabellen und macht weder Preisabfragen noch
    KI-Aufrufe. Übernommen wird nur eine feste Feld-Whitelist — TUI-URL,
    Buchungscodes, PDF-Links und Wunsch-/Buchungspreise bleiben draußen.
  - Links laufen ab (Standard 30 Tage, 1–365 einstellbar), lassen sich
    verlängern und jederzeit widerrufen. Token mit 72 Bit Entropie,
    `noindex`-Header, strikte CSP, Bremse gegen Token-Raten.
- Neue Optionen `enable_public_share`, `public_port`, `public_base_url`,
  `public_share_days`.

### Changed
- Der Markdown-Renderer für KI-Texte liegt jetzt in `static/aimd.js` und wird
  von der Hauptseite **und** der öffentlichen Seite genutzt (vorher nur in
  `app.js`) — kein zweiter, driftender Renderer.

## [0.75.4] - 2026-08-06

### Fixed
- **Kopfzeile überlappte** — die Countdown-Pille („✈ Ziel · noch X Tage")
  wuchs über ihre Rasterspalte hinaus und schob sich über Logo und
  Knöpfe. Sie wird jetzt bei Platzmangel abgeschnitten (…), am Handy
  steht sie in einer eigenen Zeile unter Logo und Knöpfen.
- **Versionsnummer in `app.py`** hing auf 0.75.0 fest (seit v0.75.1 nicht
  mitgezogen) — die Anzeige im Add-on zeigte eine falsche Version.

### Changed
- **„Alle prüfen" und „KI-Verlauf" nur noch als Symbol** (🔄 / 🤖) — die
  Beschriftungen sprengten die Kopfzeile auf schmalen Displays. Der Text
  steht weiterhin im Tooltip.

## [0.75.3] - 2026-08-06

### Fixed
- **Handy-Ansicht überarbeitet** — auf schmalen Displays waren Kopf-,
  Werkzeug- und Karten-Knopfleiste einzeilig zusammengequetscht, die
  Beschriftungen nur noch Stummel („Prü…", „Verl…", „Aktionscod…").
  Jetzt brechen alle Leisten um (zwei Knöpfe pro Zeile), die Preis-Spalte
  rutscht unter die Angebotsdaten, das Hotelbild nutzt die volle Breite
  und Wunschpreis/Gebuchter Preis passen in je eine Zeile. Auch am Tablet
  (bis 767 px) werden Leisten umgebrochen statt abgeschnitten.
- **Preiskalender am Handy** — das 7-Spalten-Raster war breiter als der
  Bildschirm; die Preise stehen dort jetzt ohne Nachkommastellen
  („2.132 €"), damit alle Wochentage sichtbar bleiben.

### Changed
- **Preis-Aufschlüsselung** — der Zusatz „— sonst erst im Checkout
  sichtbar" bei den Veranstalter-Hinweisen entfällt.

## [0.75.2] - 2026-08-05

### Fixed
- **Unterstrich bei Link-Buttons entfernt** — „📄 PDF öffnen" und
  „📅 Kalender" in „Meine Reisen" sind Links (`<a class="btn">`) und wurden
  vom Browser unterstrichen. Jetzt sehen sie aus wie alle anderen Buttons.

## [0.75.1] - 2026-08-05

### Changed
- **Footer zweizeilig** — die KI-Einträge (⚙ KI-Prompts, aktiver Anbieter,
  KI-Kosten) stehen jetzt in einer eigenen zweiten Zeile statt in einem
  langen Umbruch. Bei deaktivierter KI entfällt die Zeile komplett.

## [0.75.0] - 2026-08-05

### Added
Das Preis-Aufschlüsselungs-Fenster (Rechtsklick auf den Preis) zeigt jetzt alles,
was das Buchungssystem über die konkrete Buchung verrät:

- **⚠ Veranstalter-Hinweise (Errata)** — Infos, die sonst erst im Checkout
  auftauchen: Wasserflugzeug-Zeitfenster, Gepäcklimits auf Inlandsflügen,
  Sicherheitshinweise (z. B. fehlende Balkongeländer an Wasserbungalows) u. v. m.
  Aufklappbar, damit das Fenster kompakt bleibt.
- **Bestätigte Flugverbindungen** je Richtung mit allen Segmenten (Umsteigen
  sichtbar, z. B. STR→VIE→MLE), Zeiten, Flugnummern und **Buchungsklasse** —
  ein Klassenwechsel erklärt oft einen Preissprung.
- **Badges:** ✈ Charter-/Linienflug, 💺 Sitzplatz reservierbar (oder nicht),
  🛎 Sonderleistungen buchbar, 🏨 TUI-Kontingent vs. Bettenbank (z. B. DBH/MTS —
  erklärt abweichendes Preis-/Stornoverhalten).
- **Alarm „Buchungsdetails geändert"** (Option `notify_booking_changes`,
  Standard an): ändern sich Flugzeiten, Flugnummern oder Buchungsklasse
  gegenüber dem letzten Poll — oder die Veranstalter-Hinweise — kommt eine
  Meldung mit vorher/jetzt über HA/Telegram, plus Marker im Verlauf-Diagramm.
  Die Erstbefüllung bleibt bewusst still, gemeldet werden nur echte Übergänge.

## [0.74.1] - 2026-08-05

### Fixed
- **Preis-Aufschlüsselung zeigte „Rückflug 0 €"** bei Linienflug-Angeboten
  (z. B. Austrian zu den Malediven): kein Auslesefehler — bei Retour-Tarifen
  bepreist das TUI-Buchungssystem beide Flüge zusammen auf **einem** Leg, das
  andere steht echt mit 0 € drin (Charterflüge wie TUIfly haben dagegen je Leg
  einen Preis). In dem Fall steht jetzt eine gemeinsame Zeile
  „✈ Flüge (Hin & Rück)" mit dem Gesamtflugpreis samt Erklärungs-Tooltip statt
  der verwirrenden 0.

## [0.74.0] - 2026-08-05

### Added
- **🔮 Preisprognose im Verlauf-Fenster** (heuristisch, ohne KI-Kosten): eine
  gestrichelte Kurve setzt den Preisverlauf 7/14/30 Tage in die Zukunft fort.
  Grundlage ist die **Kalender-Historie desselben Angebots** — sie enthält für
  viele Reisetermine, wie sich deren Preis mit schrumpfender Vorlaufzeit
  entwickelt hat (Median-Kurve je 7-Tage-Bucket „Tage vor Abreise") — plus der
  **regionale Markttrend** der letzten 14 Tage als Drift. Unter dem Diagramm
  steht die Prognose als Zahl mit Basisangabe und ausdrücklich als **Annahme**
  markiert. Fehlen Kalenderhistorie **und** Markttrend, sagt TUIWatch ehrlich
  „zu wenig Daten" statt zu raten; einzelne Horizonte ohne Datenbasis werden
  weggelassen. Neuer Endpoint `GET /api/forecast/<offer_id>`.

## [0.73.0] - 2026-08-05

### Added
- **📊 Tracking-Statistik** (neuer Footer-Eintrag, `GET /api/stats`): Ersparnis
  gegenüber dem Höchstpreis je aktivem Angebot (mit Summe), die größten
  Einzelbewegungen zwischen zwei Prüfungen, **Preisänderungen nach Wochentag**
  (Anzahl, ↓/↑, Ø-Richtung — Basis Markttrend-Daten), gebuchte Angebote vs.
  heutiger Preis und die **Tiefstpreis-Rückschau**: bei abgeschlossenen
  (archivierten) Angeboten lag der Tiefstpreis im Median X Tage vor Abreise —
  erste empirische Antwort auf „wann buchen?". Neues Modul `stats_routes.py`.

## [0.72.0] - 2026-08-05

### Added
- **ICS-Kalender-Export für „Meine Reisen":** 📅-Knopf im Reisen-Fenster lädt
  alle Reisen als `.ics`-Datei (`GET /api/trips/ics`), in der Detailansicht gibt
  es den Export je Reise (`…/<id>/ics`). Ganztägiger Termin von An- bis
  Abreisetag, mit Buchungsnummer, Nächten, Reisenden und Gesamtpreis in der
  Beschreibung — importierbar in HA-Kalender, Google Kalender, Outlook & Co.

## [0.71.0] - 2026-08-05

### Added
- **Suchabo-Meldungen zeigen jetzt den Unterschied zum letzten Lauf:** 🆕 für
  Hotels, die erstmals unter die Schwelle gerutscht sind, 📉 mit „vorher X €,
  −Y €" für bereits gemeldete, die weiter gefallen sind — Kopfzeile z. B.
  „2 neu, 1 billiger unter 1.500 €". Vorher stand nur eine Mischliste da,
  ohne zu sehen, was sich getan hat. Dieselben Marker stehen in der
  Trefferliste im UI (🆕 bzw. 📉 −50 € am Hotelnamen).

## [0.70.0] - 2026-08-05

### Added
- **Push aufs Handy: frei wählbarer HA-Notify-Dienst** (`ha_notify_service`).
  Bisher landeten HA-Meldungen nur als persistente Benachrichtigung in der
  HA-Oberfläche — auf dem Handy sah man nichts. Mit z. B.
  `mobile_app_mein_handy` geht jetzt jede Meldung zusätzlich als Push über die
  Companion-App raus. Mehrere Dienste kommagetrennt, `notify.`-Präfix optional,
  leer = Verhalten wie bisher. Die persistente Benachrichtigung bleibt immer
  bestehen (sie trägt weiter das 🔔-Panel im UI).
- Backlog um Check24-GIATA-Auto-Mapping, cert_expiry-Debug und app.js-Aufteilung
  ergänzt.

## [0.69.1] - 2026-08-05

### Added
- **Die vier neuen Endpoints stehen mit im API-Selbsttest** (Ampel im Footer):
  Buchbarkeit (vacancy-check), Gepäck, Zahlungskonditionen, Zuletzt-gebucht —
  alle als *nicht kritisch* (kein `notify_api_errors`-Alarm, nur gelbe Ampel).
  Wichtig vor allem als Drift-Wächter für den vacancy-check: ändert TUI das
  Payload-Format (wie beim travelType-Objekt), meldet der Endpoint dauerhaft
  FAILED — ohne Selbsttest bliebe der „Nicht mehr buchbar"-Alarm einfach still
  tot. Der Buchbarkeits-Check nutzt das Testangebot aus dem Preis-Check weiter,
  der Zahlungs-Check testet nebenbei den Hotel-Content-Endpoint (Ländercode).

## [0.69.0] - 2026-08-05

### Added
- **Preis-Aufschlüsselung Hotel / Hinflug / Rückflug** je Angebot — Daten, die die
  TUI-Angebotsseite selbst nie anzeigt. Quelle ist der `vacancy-check`-Endpoint
  (das, was der Knopf „Verfügbarkeit prüfen" auf tui.com auslöst): er antwortet
  live aus dem Veranstaltersystem (ATCOMRES) mit dem bestätigten Gesamtpreis,
  aufgeteilt in Hotel- und Fluganteile. Wird bei jeder Prüfung mit erfasst und
  je Messpunkt gespeichert — damit ist erstmals sichtbar, **ob eine Preisänderung
  vom Hotel oder vom Flug kommt.** Wichtig: die Flugpreise im normalen Offer-JSON
  sind dafür unbrauchbar (dort stand für denselben Flug 45 € statt live 235 €).
- **Rechtsklick auf den Preis** öffnet die Aufschlüsselung (Linksklick bleibt
  Check24): Hotel/Hinflug/Rückflug mit Summe, dazu **Inklusiv-Gepäck** (z. B.
  „1×20 kg p. P."), **Anzahlung und Restzahlungstermin** (z. B. „25 % · Rest bis
  21.09.2026") und „Hotel zuletzt von anderen gebucht". Gepäck und
  Zahlungskonditionen sind quasi-statisch und werden nur einmal je Angebot geholt.
- **Verfügbarkeit ist jetzt live bestätigt statt nur abgeleitet:** bisher hieß
  „verfügbar" nur „die Offer-API lieferte Treffer". Bei bestätigten Angeboten
  zeigt das Badge „⚡ verfügbar · bestätigt"; bestätigt das Buchungssystem ein
  Angebot nicht mehr, erscheint „⚠ nicht bestätigt".
- **Alarm „nicht mehr buchbar?"** (Option `notify_unavailable`, Standard an):
  meldet über HA/Telegram den Übergang bestätigt → nicht bestätigt (evtl.
  ausgebucht) und gibt Entwarnung, sobald das Buchungssystem wieder bestätigt.
  Bewusst nur der Übergang: ein FAILED ohne vorheriges OK kann auch API-Drift
  sein und wäre als Ausverkauft-Meldung falscher Alarm.
- Verlaufstabelle und CSV-Export enthalten die neuen Spalten Hotel/Hin/Rück.
- Alles ohne Browser: reine JSON-Aufrufe (~0,5 s), Playwright war nur das
  Erkundungswerkzeug. Neue Endpoints in [SCRAPING.md](SCRAPING.md) dokumentiert —
  inklusive der Stolperfalle, dass `travelType` im vacancy-Payload ein Objekt
  sein muss (als String antwortet der Endpoint mit FAILED) und paymentService
  den Header `X-Agency` verlangt.

## [0.68.1] - 2026-08-05

### Added
- **Grüner Rahmen am „Reiseführer"-Knopf**, wenn zu diesem Ziel schon einer
  gespeichert ist — sonst sieht man einem Angebot nicht an, ob der Klick nur
  nachschlägt oder einen KI-Aufruf auslöst. Abgeglichen wird über den Ziel-Namen:
  die Angebotsliste kennt nur die Hotel-giataId, und die Region je Angebot einzeln
  aufzulösen wäre ein Fremdaufruf pro Zeile.
- **Tokens und Kosten stehen jetzt auch unter Reiseführer und Klimatabelle** —
  dieselbe Zeile wie bei jedem anderen KI-Ergebnis (Input-/Output-Tokens,
  Websuchen, geschätzte Kosten, Gesamtsumme). Nur beim frisch erzeugten Ergebnis:
  kommt es aus der Datenbank, hat es nichts gekostet. In der Gesamtanzeige der
  Fußzeile war beides schon immer enthalten (beide Routen zählen über
  `_record_ai_usage`), sichtbar war es im Fenster aber nicht.

## [0.68.0] - 2026-08-05

### Added
- **Reiseführer je Reiseziel (KI).** Neuer Knopf **Reiseführer** an jedem Angebot,
  in der Suchmaske und als 🧭 in der Kopfzeile. Dreizehn Abschnitte: Allgemeines
  (Währung, Wechselkurs, Zeitzone, Flugzeit, Steckdosen), Einreise, Klima,
  Gesundheit, Geld, Mobilität, Internet, Sicherheit, Kultur & Etikette, Don't Dos,
  Insider-Tipps, Praktisches und 20 nützliche Wörter — dazu eine Kurzfassung in
  höchstens 15 Stichpunkten und Sprungmarken über den Abschnitten.
- **Die gespeicherte Klimatabelle steht mit im Reiseführer** — Diagramm und
  Monatstabelle, im Fenster wie im Ausdruck und in der E-Mail. Beide hängen an
  derselben Region-giataId, damit sie zusammenfinden.
- **Drucken und E-Mail-Versand** des Reiseführers. Der Druck läuft über ein
  verstecktes iframe mit eigenem Stylesheet statt über ein Popup — im HA-Ingress
  läuft die Oberfläche selbst in einem iframe, ein Popup würde dort blockiert.
- Angaben, die schnell veralten (Einreisebestimmungen, Wechselkurs, Preise,
  Sicherheitslage), sind mit **⏱** markiert — ein Monate alter Wechselkurs wäre
  sonst nicht als solcher zu erkennen.
- Wie die Klimatabelle wird der Reiseführer **einmal je Ziel** erzeugt und dauerhaft
  gespeichert; Neuerstellung nur über „🔄 Neu abrufen". Anders als beim Klima wird
  **nicht** im Hintergrund vorgeladen: der Reiseführer ist der teuerste Einzelaufruf
  im Add-on, einer je gesuchtem Ziel wäre Geldverbrennung.

### Changed
- **„Pausieren" und „Archivieren" in der Angebotsliste sind jetzt Symbole** (⏸/▶
  und Archivkasten, Beschriftung im Tooltip). Die Zeile war mit elf beschrifteten
  Knöpfen zu voll für einen weiteren.

## [0.67.2] - 2026-08-05

### Added
- **Hotelfotos sind mit den Pfeiltasten ← / → blätterbar.** Bisher öffnete ein Klick
  auf ein Foto der GIATA-Galerie nur ein einzelnes Vollbild — für das nächste Foto
  musste man zurück ins Raster. Die Lightbox kennt jetzt die ganze Fotoliste: ← / →
  oder die beiden Pfeilflächen blättern umlaufend durch, eine Zählanzeige
  („3 / 24") zeigt die Position, und das jeweils nächste und vorherige Bild wird
  vorgeladen. Bei nur einem Foto bleiben Pfeile und Zähler ausgeblendet.

### Fixed
- **Abo-Glocke im Dropdown der gespeicherten Suchen steht jetzt hinter dem Namen.**
  Davor schob sie die Namen der Abos gegenüber den übrigen Einträgen ein und zerriss
  die linke Kante der Liste.
- **Quellen-Marker in der Klimatabelle sind anklickbar.** Perplexity setzt Marker wie
  „[7][11]" auch in die Textfelder strukturierter Antworten; dort ließen sie sich
  beim Abruf nicht verlinken (das hätte den JSON-String zerstört) und blieben als
  toter Text stehen. Die Quellen-URLs werden jetzt durchgereicht und die Marker nach
  dem Parsen verlinkt — in Zusammenfassung, Monatshinweisen und in der E-Mail.

## [0.67.0] - 2026-08-05

### Fixed
- **Klima-Fenster blieb bei aktivierter Prompt-Vorschau komplett leer** — keine
  Tabelle, keine Fehlermeldung, kein Log-Eintrag. Ursache: bei aktiver Option
  `ai_prompt_preview` antwortet die Route erst mit dem Prompt statt mit Daten. Das
  Klima-Fenster rief sie mit einem nackten `fetch` auf, bekam HTTP 200 mit
  `{prompt_preview:…}` und rendete eine leere Tabelle — der KI-Aufruf fand nie statt.
  Jetzt läuft der Abruf über den Vorschau-Mechanismus, und die Vorschau wird **im
  Klima-Fenster** gerendert (die Standardvariante schreibt sie ins KI-Ergebnis-
  Fenster, das hier gar nicht offen ist — sie wäre unsichtbar geblieben und der
  Ladebalken hätte ewig gedreht).
- Der **automatische Abruf nach einer Suche** überspringt die Vorschau bewusst, wie
  alle anderen Hintergrundläufe (Wochenüberblick, Aktionscodes, Auto-Tagging) — sonst
  poppte nach jeder Suche ungefragt ein Dialog auf.
- Fehlen die Monatsdaten, erscheint jetzt eine erklärende Meldung statt einer
  Tabelle mit bloßer Kopfzeile.

### Added
- **Teuerster Termin im Preiskalender**, als Gegenstück zum günstigsten: ohne ihn
  sagt der günstigste nichts darüber, wie viel die Wahl des Reisedatums überhaupt
  ausmacht. Dazu die **Spanne** zwischen beiden. Die Zusammenfassungs-Einträge sind
  jetzt **anklickbar** — der Kalender springt zum Monat, hebt den Tag kurz hervor
  und öffnet dessen Preisverlauf. Bereits gespeicherte Kalender bekommen den Wert
  nachgerechnet, ohne Neuabruf.
- **Klimatabellen von der Hauptseite abrufbar** über den neuen **🌤**-Knopf in der
  Kopfzeile: Liste aller gespeicherten Ziele mit Erstellungsdatum, Klick öffnet die
  Tabelle, 🗑 löscht sie. Neuer Endpunkt `GET /api/climate`.

### Changed
- **Der „Frage"-Knopf zeigt nur noch das Symbol** ❓ (Beschriftung in den Tooltip
  gewandert), damit die Kopfzeile mit dem neuen 🌤-Knopf nicht überläuft.

## [0.66.0] - 2026-08-05

### Added
- **🌤 Klima-Knopf in der Suchmaske.** Klimatabelle des Reiseziels über alle zwölf
  Monate: Tages- und Nachttemperatur, **Wassertemperatur**, Sonnenstunden pro Tag,
  Regentage, ein kurzer Hinweis je Monat (Regenzeit, Passatwind, Hochsaison …) und
  die aus Wetter-Sicht besten Monate.
  - **Dauerhaft in der Datenbank gespeichert** (neue Tabelle `climate`), einmal je
    Ziel erzeugt. Klimawerte sind langjährige Mittel, kein Wetterbericht — ein
    erneuter KI-Aufruf brächte nur Kosten. Jeder weitere Abruf kommt aus der DB;
    **🔄 Neu abrufen** erzwingt eine Neuberechnung.
  - **Nach jeder Suche automatisch vorgeladen**, sofern eine KI konfiguriert ist. Dank
    der Speicherung ist das je Ziel genau ein Aufruf, kein Dauerverbrauch. Der
    Lese-Endpunkt `GET /api/climate/<giata>` ruft nie die KI — die Suchmaske fragt ihn
    bei jedem Suchlauf an.
  - **Diagramm plus Tabelle:** zwei Panels mit gemeinsamer Monatsachse (Temperaturen
    als Linien, Regentage als Säulen — bewusst keine zwei y-Achsen in einem Bild),
    Werte des überfahrenen Monats als Zeile darüber, Reisemonate hervorgehoben.
    Serienfarben aus einer CVD-geprüften Palette, in Hell und Dunkel eigens gesetzt.
  - **✉ Als E-Mail** verschickt die gespeicherte Tabelle (ohne KI-Aufruf). Die Mail
    enthält nur die Tabelle: Mail-Clients rendern inline-SVG nicht zuverlässig.
  - Neue Routen: `POST /api/ai/climate`, `GET`/`DELETE /api/climate/<giata>`,
    `POST /api/climate/<giata>/email`.

### Fixed
- **ESC schloss beim Empfänger-Dialog das falsche Fenster.** Der Dialog bekommt beim
  Öffnen `z-index: 60` und liegt damit über dem Fenster, aus dem er aufgerufen wurde,
  wurde in der ESC-Reihenfolge aber weit hinten geprüft — aus der Suchmaske heraus
  schloss ESC also die Suche und ließ den sichtbaren Dialog stehen.

## [0.65.1] - 2026-08-05

### Fixed
- **„Heute"-Knopf in der Suchmaske lieferte nie Treffer.** Er setzte das Startdatum
  exakt auf heute — darauf antwortet TUIs Such-API aber mit HTTP 500, das Ergebnis
  war immer leer. Er setzt jetzt **heute + 2 Tage** und heißt passend
  **„Frühestens"**. Live gemessen (Gran Canaria, 7 Nächte): heute = Fehler,
  heute+1 = 53 Treffer, heute+2 = 132, heute+3 = 144 — zwei Tage sind der Punkt, ab
  dem das Angebot brauchbar ist. Ein früheres Datum lässt sich weiterhin von Hand
  eintragen.

## [0.65.0] - 2026-08-05

### Added
- **🤖 Reisezeit-Check in der Suchmaske** (Knopf neben „Suchen"). Prüft vor dem
  Buchen die Eckdaten der Suche in vier Punkten:
  1. **Reisezeit** — taugt der gewählte Zeitraum für dieses Ziel? Regen-/Trockenzeit,
     Temperaturen (Luft und Wasser), Luftfeuchtigkeit, Wind, Hurrikan-/Monsun-/
     Zyklonsaison, mit konkreten Werten statt Allgemeinplätzen.
  2. **Saison und Preisniveau** — Haupt-, Neben- oder Zwischensaison, die
     Schnäppchenmonate des Ziels samt grober Ersparnis, dazu Schulferien, Feiertage
     und lokale Großereignisse.
  3. **Besserer Zeitraum?** — ein konkreter Alternativtermin, wenn einer deutlich
     mehr fürs Geld böte; passt der gewählte schon, sagt die KI das ebenso klar,
     statt eine Alternative zu konstruieren.
  4. **Ähnliche Ziele** — 2 bis 4 Alternativen mit vergleichbarem Charakter
     (Flugzeit ab dem gewählten Abflughafen, Klima zur Reisezeit, Preisniveau), je
     mit Vor- **und** Nachteil gegenüber dem Wunschziel.

  Mitgeschickt werden nur die Maskendaten; wurde bereits gesucht, zusätzlich eine
  kurze Preisstatistik der Treffer (Anzahl, günstigster, Median, teuerster) — ohne
  die könnte die KI zum Preisniveau nur allgemein raten. Neue Route
  `POST /api/ai/search-advice`, Verlaufs-Kind `search_advice`.

### Fixed
- **ESC schloss beim KI-Ergebnis das falsche Fenster.** Das Ergebnis-Fenster steht
  im DOM hinter Suchmaske, Kalender und Vergleich und liegt daher optisch darüber,
  wenn es aus einem von ihnen geöffnet wird — geprüft wurde es aber erst nach ihnen.
  Ein ESC schloss deshalb das darunterliegende Fenster und ließ das sichtbare offen.
  Betraf schon den KI-Vergleich und die Kalenderanalyse, nicht nur den neuen
  Reisezeit-Check.

## [0.64.1] - 2026-08-05

### Fixed
- **Reisende und Abflughafen fehlten in der versendeten Trefferliste.** Beides sind
  Suchparameter und stehen in keiner einzelnen Trefferzeile — der Mail war deshalb
  nicht anzusehen, für wie viele Personen die „pro Person"-Preise gelten und ab
  welchem Flughafen. Die Kopfzeile nennt sie jetzt:
  `Hotelsuche · Kapverdische Inseln · 2 Reisende · ab Stuttgart (STR) · Stand …`
  - Die Werte stammen aus dem Suchlauf, der die angezeigte Liste erzeugt hat (neues
    Feld `criteria` in der Antwort von `POST /api/search`), **nicht** aus dem
    aktuellen Stand der Suchmaske: die kann längst andere Werte zeigen, etwa wenn die
    Treffer aus einem Suchabo stammen. Für Abo-Treffer kommen sie aus dem Abo selbst.
  - Funktioniert in allen drei Suchwegen — Maske, eingefügte TUI-URL und „Region"
    aus einem Angebot heraus; bei den letzten beiden werden sie aus der URL gelesen.
  - Ohne Klarnamen des Flughafens (URL-/Angebotssuche) steht der IATA-Code dort.

## [0.64.0] - 2026-08-05

### Added
- **Zweiter Knopf im Frage-Fenster: „🌍 Reisefrage".** Bisher hing an ❓ Frage
  immer der Portfolio-Prompt — für „wann ist die beste Reisezeit für Sri Lanka"
  oder „was brauche ich zur Einreise nach Vietnam" war das der falsche Kontext,
  und ohne getrackte Angebote ging die Frage gar nicht erst raus.
  Das Fenster hat jetzt zwei Knöpfe, die dieselbe Frage mit unterschiedlichem
  Kontext verschicken: **📌 Portfolio fragen** (wie bisher, mit Angebotsliste) und
  **🌍 Reisefrage** (ohne Angebotsliste, dafür mit Websuche-Schwerpunkt). Die
  Beschreibung im Fenster wechselt beim Überfahren des jeweiligen Knopfes.
  - Die allgemeine Frage bekommt die Angebote bewusst **nicht** mit: sie wären
    Ballast, würden Tokens kosten und die Antwort auf die eigenen Hotels lenken.
    Sie funktioniert deshalb auch mit leerem Portfolio.
  - Ein hinterlegter Heimatort (`trippilot_home_location`) fließt für Anreise-
    und Entfernungsfragen ein.
  - Der Prompt drängt auf Websuche und auf offenes Eingeständnis von Unsicherheit
    — Einreiseregeln, Impfempfehlungen und Preise ändern sich, eine
    selbstbewusst formulierte veraltete Auskunft wäre hier schädlicher als der
    Hinweis, kurz vor Reiseantritt gegenzuprüfen.
  - Technisch über `scope` an `POST /api/ai/ask` (unbekannte Werte fallen auf
    `portfolio` zurück). Eigenes Verlaufs-Kind `ask_general`, im KI-Verlauf als
    „🌍 Reisefrage" ausgewiesen und dort wie gewohnt wiederholbar; die
    Portfolio-Frage heißt dort jetzt „📌 Portfolio-Frage".

## [0.63.0] - 2026-08-05

### Changed
- **„Warenkorb" heißt jetzt „Preisbarometer" 🌡️** — der Begriff aus der
  Statistik-Fachsprache (Warenkorb = feste Gütermenge zur Preismessung) war
  außerhalb davon eher irreführend. Ein einzelner Eintrag heißt jetzt
  **Messreihe** (je gespeicherter Suche eine). Reine Umbenennung der Anzeige- und
  Log-Texte: Optionsnamen (`market_basket_*`), API-Routen, Datenbankspalten und
  Sensor-Attribute bleiben unverändert — bestehende Konfigurationen und
  Automationen laufen unberührt weiter.

## [0.62.0] - 2026-08-05

### Changed
- **Warenkorb hat ein eigenes Fenster.** Beide Trends in einem Markttrend-Fenster
  übereinander waren unübersichtlich — sie zählen unterschiedlich (Warenkorb-Tage
  gegen Preisänderungs-Datenpunkte) und luden zum Verwechseln ein. Das
  Markttrend-Fenster zeigt jetzt nur noch den Trend der getrackten Angebote, eine
  Zeile nennt den Warenkorb-Gesamtwert, und der Knopf **🧺 Warenkorb** öffnet das
  neue Fenster mit Tabelle, „Sammelt noch"-Liste, Fortschrittsbalken und
  **🧺 Jetzt füllen**.
- **Konsole fasst 2000 statt 200 Zeilen.** Ein einziger Warenkorb-Lauf schreibt bei
  vielen gespeicherten Suchen über hundert Zeilen — der interessante Teil war raus,
  bevor man nachsehen konnte. Der Warnungs-/Fehlerpuffer wächst von 100 auf 500.
- **Neuer Konsolen-Tab unter „🔔 Meldungen & Fehler"** (`/api/logs`): das komplette
  Log seit dem Start, **durchsuchbar nach Text und Log-Stufe**, serverseitig
  gefiltert. Das Overlay-Panel per Logo-Doppelklick bleibt der Live-Ticker und holt
  nur noch die letzten 500 Zeilen (`/api/console?limit=`) — es rendert im
  2-Sekunden-Takt komplett neu, der volle Puffer wäre dort Verschwendung. Ein
  Hinweis im Panel verweist auf den Tab, wenn ältere Zeilen vorhanden sind.

## [0.61.1] - 2026-08-04

### Fixed
- **Kleine Warenkörbe blieben dauerhaft ohne Trend.** Ein Tag zählte nur mit
  mindestens 10 vergleichbaren Hotels — bei stark gefilterten Suchen (nur All
  Inclusive, Direktflug ab STR, bestimmte Lage) bleiben aber oft nur 11–16 Treffer
  übrig, und ein einziger Verpflegungswechsel bei zweien ließ den Tag durchfallen.
  Die Mindestbreite richtet sich jetzt nach der Warenkorbgröße: 60 % des kleineren
  der beiden Snapshots, höchstens 10, mindestens 5. Große Warenkörbe bleiben streng,
  schrumpfende (Saisonende) ziehen die Schwelle mit.
- **Angebots-Warenkörbe je Region und Abreisemonat gebündelt** statt je Einzeltermin.
  Fünf getrackte Gran-Canaria-Angebote mit Abreise am 3., 7. und 31. Mai sowie 7. und
  14. Juni ergaben fünf Warenkörbe à ~220 Hotels und je fünf Ergebnisseiten — 25
  Abrufe täglich für praktisch denselben Markt. Jetzt zwei Warenkörbe („Mai 2027,
  11 Nächte" / „Juni 2027, 11 Nächte") mit 10 Abrufen. Die Dauer bleibt im Schlüssel,
  weil eine und zwei Wochen unterschiedliche Preisniveaus haben. Das Suchfenster endet
  am Monatsletzten **plus Reisedauer**, sonst fielen genau die Abreisen am Monatsende
  heraus (`endDate` meint bei der Such-API die späteste Rückreise). Live geprüft:
  Mai-Warenkorb 227 Hotels mit Abreisen vom 01.05. bis 31.05.
  Die Snapshots der Einzeltermin-Fassung werden einmalig verworfen — zu ihren
  Schlüsseln gibt es keinen Warenkorb mehr, sie blieben sonst als Karteileichen unter
  „sammelt noch" stehen.

## [0.61.0] - 2026-08-04

### Changed
- **Warenkorb richtet sich nach den Terminen der gespeicherten Suchen** statt nach
  einer konstanten Vorlaufzeit. Bisher suchte er stur für „heute + 91 Tage" — der
  Abreisetag wanderte also täglich weiter. Statistisch sauber, praktisch wertlos:
  wer seinen Urlaub im **Mai** plant, dem hilft die Preisbewegung eines täglich
  anderen Termins nicht bei der Frage, ob er jetzt buchen soll.
  Jetzt läuft **1×/Tag genau die gespeicherte Suche** noch einmal — mit ihren
  Reiseterminen, ihrer Dauer und ihren Filtern (Sterne, Weiterempfehlung,
  Verpflegung, Flughafen …). Der Trend sagt damit: „alle Hotels für meinen
  Mai-Termin auf Teneriffa sind diese Woche 3 % gefallen."
  - **Ein Warenkorb je Suche**, nicht je Region — zwei Suchen für dasselbe Ziel mit
    verschiedenen Terminen sind zwei verschiedene Märkte.
  - **Getrackte Angebote ohne gespeicherte Suche** bekommen ihren Termin aus dem
    Angebot selbst (Rückreisedatum minus Dauer). `market_basket_lead_days` ist nur
    noch Rückfallebene, wenn gar kein Datum vorliegt.
  - **Abgelaufene Reisezeiträume** fallen automatisch raus.
  - Das Abreise**datum** ist bewusst kein Match-Kriterium mehr: sucht die Suche über
    einen Zeitraum, ist der günstigste Termin darin genau die interessante Zahl.
  - Die bisher gesammelten Warenkorb-Daten haben eine andere Preisbasis und werden
    beim Update **einmalig verworfen** (Trend beginnt neu). Backup-Version 7;
    Warenkorb-Daten aus Version-6-Backups werden aus demselben Grund ignoriert.
- **Fortschrittsbalken für „🧺 Warenkorb jetzt füllen"** — zeigt „X von Y Suchen",
  die bisher erfasste Hotelzahl und den gerade laufenden Warenkorb. Vorher lief der
  Vorgang minutenlang ohne jede Rückmeldung. Läuft beim Öffnen des Fensters gerade
  ein (auch automatischer) Lauf, erscheint der Balken ebenfalls. Neuer schlanker
  Endpunkt `/api/market-basket/progress` fürs Polling.
- Markttrend-Fenster nennt in der Warenkorb-Tabelle jetzt **Suchname und
  Reisezeitraum** statt der Region, und zählt darunter die Warenkörbe auf, die noch
  Daten sammeln.

## [0.60.4] - 2026-08-04

### Fixed
- **Add-on-Einstellungen erschienen komplett auf Englisch.** In der neuen
  Beschreibung zu `market_basket_lead_days` stand in `translations/de.yaml` ein
  ASCII-Anführungszeichen mitten in einem doppelt-gequoteten Text
  (`„heute + X Tage"`). Das beendet den YAML-String vorzeitig, die ganze Datei
  war unparsebar — und Home Assistant fällt in dem Fall **kommentarlos** auf
  `en.yaml` zurück, ohne Fehlermeldung oder Log-Eintrag. Zeichen korrigiert.
- **Neuer Test `tests/test_yaml_valid.py`** prüft `config.yaml` und beide
  Übersetzungsdateien auf gültiges YAML und darauf, dass jede Option in beiden
  Sprachen Name und Beschreibung hat — damit dieser stille Rückfall nicht
  wieder unbemerkt passiert.

## [0.60.3] - 2026-08-04

### Fixed
- **Warenkorb holt jede Region jetzt vollständig** statt nur der ersten vier
  Ergebnisseiten. Der feste Deckel schnitt große Regionen ab (live: Teneriffa 259
  Hotels → 200 erfasst, Algarve 287 → 200) — und weil die Such-API nach Preis
  **aufsteigend** sortiert, waren das stets die *günstigsten* 200. Hotels an
  dieser Grenze wandern täglich rein und raus; der Median hätte diese wechselnde
  Randbelegung als Preisbewegung gelesen. Paginiert wird nun bis zur gemeldeten
  Gesamttrefferzahl, mit einer Reißleine bei 1000 Hotels je Region (dann steht
  eine Warnung im Log). Nachgeprüft: Teneriffa und Algarve kommen jetzt
  vollständig an, weiterhin ein einziger Abreisetag und 7 Nächte.

## [0.60.2] - 2026-08-04

### Changed
- **Regions-Deckel des Warenkorbs von 8 auf 20 angehoben** und über die neue
  Option `market_basket_max_regions` (1…50) einstellbar. Die 8 waren defensiv
  geschätzt, bevor die echte Last bekannt war: je Region fallen 1–4 API-Aufrufe
  pro Tag an (Abbruch, sobald eine Ergebnisseite weniger als 50 Treffer liefert),
  bei acht Regionen also rund 30 Requests täglich — Kleingeld gegenüber dem
  normalen Poller.
- **Abgeschnittene Regionen stehen jetzt im Log** (mit Namen und dem Hinweis auf
  die Option). Vorher wäre eine neu angelegte Suche über dem Deckel stillschweigend
  nie im Warenkorb gelandet.

## [0.60.1] - 2026-08-04

### Fixed
- **Warenkorb-Suche lief in HTTP 500** — jede Region meldete „Suche lieferte
  keine Treffer". Ursache: der Warenkorb schickte `startDate == endDate`, um
  einen einzelnen Abreisetag zu treffen. `endDate` ist bei der Such-API aber die
  späteste **Rückreise**, nicht die späteste Abreise — zusammen mit `duration=7`
  widersprechen sich Zeitfenster und Reisedauer, die API antwortet mit 500.
  Jetzt `endDate = startDate + 7`, was die Treffer ebenfalls auf genau einen
  Abreisetag eingrenzt (live verifiziert: Gran Canaria 196 Hotels, alle mit
  demselben Abreisedatum und 7 Nächten). Ein Test hält den Abstand fest.

## [0.60.0] - 2026-08-04

### Added
- **Markttrend aus einem Regions-Warenkorb** (`market_basket.py`) — bisher
  entstand der Markttrend nur aus den Preisänderungen der eigenen getrackten
  Angebote, je Destination oft nur ein bis zwei Hotels. Neu läuft **1×/Tag je
  Region eine Hotelsuche** (bis zu 200 Hotels), aus deren Snapshots der Trend
  berechnet wird. Regionen werden automatisch aus den gespeicherten Suchen und
  den getrackten Angeboten abgeleitet, keine giataId-Pflege nötig.
  - **Matched Pairs statt Durchschnittsvergleich**: verglichen wird jedes Hotel
    mit sich selbst vom Vortag; Hotels, die nur in einem der beiden Snapshots
    stehen (ausgebucht/neu dazugekommen), zählen nicht — sonst würde der Trend
    die Zusammensetzung des Warenkorbs messen statt die Preise.
  - **Median statt Mittelwert** über die Hotel-Deltas (die Such-API liefert je
    Hotel das günstigste Angebot, dessen Zimmerkategorie unsichtbar wechseln
    kann — der Median steckt solche Ausreißer weg).
  - **Board-/Nächte-Wechsel** werden übersprungen (anderer Angebotstyp, kein
    Marktsignal).
  - **Konstante Vorlaufzeit** statt konstantem Abreisedatum: gesucht wird immer
    für „heute + `market_basket_lead_days`" (Standard 91 = Vielfaches von 7 →
    gleicher Wochentag, keine Wochenend-Preissprünge). So misst der Trend den
    Markt und nicht den Last-Minute-Effekt.
  - Verkettet wird erst auf **Tagesebene** (ein Median je Region und Tag), nicht
    über die hunderten Hotel-Deltas eines Tages.
- **Neue Optionen** `market_basket_enabled` (Standard an) und
  `market_basket_lead_days` (Standard 91, auf 14…365 begrenzt).
- **Markttrend-Fenster** zeigt beide Quellen getrennt: „🧺 Regions-Warenkorb
  (alle Hotels)" mit Hotelzahl je Destination und „📌 Deine getrackten
  Angebote" wie bisher. Neuer Button **🧺 Warenkorb jetzt füllen** stößt einen
  Lauf sofort an (läuft im Hintergrund), 🗑 je Zeile setzt eine Region zurück.
- **HA-Sensor `sensor.tuiwatch_markttrend`** nimmt den Warenkorb als Quelle,
  sobald der zwei Tagesbewegungen hat, sonst weiter den Angebots-Trend. Neue
  Attribute: `source` (basket/offers), `hotels` sowie die vollständigen
  Zweige `offers` und `basket`.
- **Wochenüberblick** (Telegram + E-Mail) enthält jetzt einen Abschnitt
  **📈 Markttrend (7 Tage)** — global und je Destination, mit Angabe der Basis
  (Warenkorb oder eigene Angebote). Fenster 7 statt 14 Tage, passend zum
  Berichtszeitraum.
- **Backup/Restore** sichert die Warenkorb-Tagesbewegungen mit
  (`tuiwatch_backup` Version 6) — der Index seit Aufzeichnungsbeginn hängt allein
  an diesen Zeilen und würde sonst bei einem Umzug wieder bei 100 anfangen. Die
  Roh-Snapshots bleiben bewusst außen vor (groß, kurzlebig, entstehen täglich
  neu). Ältere Backups ohne dieses Feld werden unverändert akzeptiert.

## [0.59.5] - 2026-07-31

### Added
- **Claude-Modell auf `claude-opus-5` umgestellt** — Nachfolger von
  `claude-opus-4-8` (gleicher Preis $5/$25 pro 1 Mio. Token, Drop-in-Upgrade
  laut Anthropic). Neuer Standard für `anthropic_model`; `claude-opus-4-8`
  komplett aus der Auswahl entfernt (Preistabellen-Eintrag bleibt für
  bereits gespeicherte alte KI-Analysen). Bestehende Configs mit
  `claude-opus-4-8` fallen automatisch auf `claude-opus-5` zurück.
- **Perplexity-Modelle geprüft** (`sonar`, `sonar-pro`, `sonar-reasoning-pro`,
  `sonar-deep-research`) — alle vier aktuell, Preise stimmen exakt mit der
  offiziellen Preistabelle überein, keine Änderung nötig.

## [0.59.4] - 2026-07-31

### Added
- **Gemini-Modelle geprüft und aktualisiert** — laut ai.google.dev/gemini-api/docs/deprecations
  wird `gemini-2.5-flash` am 16.10.2026 von Google abgeschaltet (Ersatz:
  `gemini-3.6-flash`). Bisher genutzte Modelle (`gemini-3.1-pro`,
  `gemini-3.5-flash`, `gemini-2.5-flash`) sind bis dahin weiter nutzbar und
  noch nicht entfernt. Neu wählbar: `gemini-3.6-flash` (günstiger als 3.5
  Flash, siehe Preis-Update unten). `gemini-2.5-flash` bleibt vorerst
  bestehen, sollte aber vor Oktober umgestellt werden.
- Auch die "Gemini 2.5 Pro"/"Gemini 3 Flash"-EOL-Meldung vom 31.07.2026
  geprüft — betrifft laut Quelle nur GitHub Copilots Modellauswahl, nicht
  die Gemini-API selbst; für TUIWatch (direkter API-Zugriff) nicht relevant.

### Fixed
- APP_VERSION-Konstante in app.py war beim 0.59.3-Commit nicht mitgezogen worden — jetzt nachgeholt.

## [0.59.3] - 2026-07-31
- map: `addon_config` → `app_config` (Home-Assistant-Supervisor hat `addon_config` seit 2026.07 als Legacy-Name markiert, neuer Name ist `app_config`).

## [0.59.2] - 2026-07-29

### Fixed
- **ESC schloss nur den Preiskalender, kein anderes Popup** — generischer
  Escape-Handler ersetzt die kalenderspezifische Lösung: schließt jetzt das
  jeweils oberste offene Modal (History, Vergleich, Suche, Nächte, Check24,
  Kalender inkl. Tages-Chart, Zimmer, KI-Ergebnis/-Verlauf/-Frage, TripPilot,
  E-Mail, API-Status, Prompt-Konfig, Aktionscodes, Markttrend, Reisen/-
  Jahresrückblick, GIATA-Galerie/-Lightbox) — verschachtelte Overlays (GIATA-
  Lightbox über Galerie, Tages-Chart über Kalender) zuerst, damit ein
  ESC-Druck nur eine Ebene auf einmal schließt.

## [0.59.1] - 2026-07-29

### Fixed
- **ESC schloss den Preiskalender nicht** — neuer Escape-Handler im bestehenden
  Kalender-Tastatur-Listener: schließt zuerst den Tages-Preisverlauf-Chart
  (falls offen), sonst den ganzen Kalender.
- **KI-Ladetexte zeigten wieder generisches „KI" statt Anbieternamen** —
  betraf Buchungsscore, Region-Ausblick, Kalenderpreise-Fazit, Bewertungs-Suche,
  Hotel-Vergleich, Portfolio-Frage und TripPilot. Der v0.57.10-Fix deckte nur
  den ERSTEN Ladetext ab; der zweite (nach der Prompt-Vorschau, während der
  eigentliche API-Call läuft) wurde separat als Parameter an
  `aiFetchPreviewable()` übergeben und war weiterhin hartcodiert auf „KI …" —
  jetzt ebenfalls `aiProviderName()`.
- **Gelöschte Buchungsscore-/Region-Ausblick-/Fazit-Analyse im KI-Verlauf kam
  bei erneutem Klick zurück** — `DELETE /api/ai/history/<id>` entfernte nur
  die `ai_analyses`-Zeile, nicht den bis zu 6h gültigen In-Memory-Cache
  (`_booking_score_cache`/`_region_outlook_cache`/`_ai_summary_cache`), der
  weiterhin den gelöschten Stand auslieferte. Löscht jetzt zusätzlich jeden
  Cache-Eintrag, dessen gespeicherte `id` zur gelöschten `aid` passt.

## [0.59.0] - 2026-07-29

### Added
- **Benachrichtigungen pro Angebot stummschaltbar (🔔/🔕)** — neuer Glocken-Button
  oben neben dem Preis auf der Angebotskarte schaltet HA-/Telegram-Versand für
  dieses Angebot aus (Preisänderung, Wunschpreis, Günstigerer Termin, Günstiger
  als gebucht), ohne die Preisprüfung selbst zu pausieren. Zweite, unabhängige
  Glocke im Preiskalender-Modal schaltet nur die "Kalenderpreise geändert"-Alarme
  (`price_calendar.py`) stumm. Die 🔔-Übersicht ("Meldungen & Fehler" im UI) zeigt
  stummgeschaltete Meldungen weiterhin an — nur der externe Versand entfällt.
  Neue Spalten `notify_muted`/`notify_calendar_muted` auf `offers` (Migration für
  Bestands-DBs), PATCH `/api/offers/<id>` akzeptiert beide Felder.

## [0.58.2] - 2026-07-29

### Fixed
- **Preisverlauf-Diagramm im Preiskalender (Klick auf 📈 an einem Tag) zeigte
  keine Preise** — `drawChart()` zeichnet Achsenbeschriftung/Gitterlinien nur
  im `full`-Modus; der Kalender-Tages-Chart rief mit `full=false` auf (gedacht
  für kompakte Sparklines), obwohl das Modal mit 120px Höhe genug Platz für
  echte Beschriftung hat. Jetzt `full=true`, gleicher Zeichenpfad wie beim
  normalen Preisverlauf-Chart.

## [0.58.1] - 2026-07-28

### Fixed
- **cert_expiry-Sensor (`tuiwatch.gizmonet.cloud`) trotz 0.58.0 weiterhin
  gelegentlich `unavailable`** — `_scrape_lock`/`_check24_scrape_lock`
  serialisieren jeden `fetch_price`-Aufruf über Hintergrund-Poller UND
  manuelle UI-Aktionen (Zimmer-/Nächte-Vergleich, Check24) hinweg. Bei
  mehreren gleichzeitig wartenden Requests konnten alle 8 waitress-Threads
  im Lock-Wait stecken bleiben, sodass keine Kapazität mehr für neue
  Verbindungen (inkl. Docker-HEALTHCHECK) übrig blieb. Thread-Pool auf 32
  angehoben — die Locks bleiben (Chromium-Fallback/Check24-Scrape sollen
  weiter nur einzeln laufen), aber wartende Requests blockieren jetzt
  keinen knappen Ressourcen-Engpass mehr.

## [0.58.0] - 2026-07-24

### Fixed
- **Externer cert_expiry-Sensor (`tuiwatch.gizmonet.cloud`) wurde wiederholt
  `unavailable`** — Ursache war Flasks eingebauter Dev-Server (`app.run`),
  der neue Verbindungen spürbar verzögert annahm, während einer der fünf
  Hintergrund-Worker (Preis-Poller, Aktionscodes, Health, Cooldown,
  Markttrend) sequenziell externe TUI-APIs abfragte — teils über eine
  Stunde am Stück. Der externe TLS-Check lief dabei in den Timeout. Webserver
  läuft jetzt über `waitress` mit eigenem Thread-Pool, unabhängig von der
  Auslastung der Hintergrund-Worker.

## [0.57.10] - 2026-07-22

### Fixed
- **KI-Ladetext zeigte generisches „KI" statt echtem Anbieternamen (Claude/Gemini)**
  — beim allerersten KI-Aufruf nach dem Laden der Seite war `_aiActiveProvider`
  noch nicht vom Server geladen (asynchroner Hintergrund-Fetch), `aiProviderName()`
  fiel dadurch auf den generischen Fallback zurück. Betraf Buchungsscore,
  Region-Ausblick, Kalender-Analyse, KI-Fazit, KI-Vergleich und „Frag dein
  Portfolio" — TripPilot wartete bereits korrekt. Jetzt warten alle sechs
  Ladetexte per `ensureAiProviderLoaded()` auf den geladenen Anbieternamen,
  bevor der Ladetext gebaut wird.

## [0.57.9] - 2026-07-22

### Fixed
- **Ganze Monate fehlten in der Buchungsscore-Monatsliste (v0.57.8-Nachbesserung)**
  — bei Angeboten mit wöchentlichem statt täglichem Flugrhythmus (z. B. nur
  Sonntagsflüge) hat mancher Monat nur 1-2 Termine. Die Mindestschwelle von 3
  Terminen (gedacht als Ausreißer-Schutz für Günstigster/Teuerster-Monat) hatte
  solche Monate komplett aus der neuen vollen Monatsliste getilgt — u. a. fehlte
  dadurch der Zielmonat selbst. Schwelle gilt jetzt nur noch für die
  Extremwert-Auswahl; die volle Liste zeigt alle Monate mit mind. 1 Termin plus
  Terminanzahl, damit die KI dünn belegte Monate vorsichtiger gewichten kann.

## [0.57.8] - 2026-07-22

### Fixed
- **Buchungsscore wertete Preisunterschiede zwischen Reisemonaten teils falsch aus**
  — die Saisonalität aus dem Preiskalender enthielt bisher nur den günstigsten
  und teuersten Monat als Ø-Preis. Lagen Zielmonat und Vergleichsmonat beide
  dazwischen (z. B. Sept. 2026 vs. Feb. 2027), sah die KI nur die einzelnen
  Preisbewegungen (`calendar_moves`, reine Deltas) ohne die absoluten
  Monatsdurchschnitte — sie konnte den echten €-Abstand zwischen den Monaten
  nicht direkt ablesen. Prompt liefert jetzt zusätzlich die volle
  Monatsdurchschnittsliste (alle Monate, nicht nur die zwei Extreme).

## [0.57.7] - 2026-07-19

### Fixed
- **sensor.tuiwatch_markttrend weiterhin unavailable trotz kurzem Refresh** —
  echte Ursache: die Trend-/Index-Berechnung (DB-Queries, Datums-Parsing,
  Divisionen je Region) lief bislang außerhalb jeder Absicherung. Crashte sie
  bei einer ungewöhnlichen Datenkonstellation (z. B. eine einzelne Region),
  flog die Exception unkontrolliert aus der Funktion — **kein POST fand statt**,
  lautlos (nur ein Log-Eintrag im äußeren Worker, leicht zu übersehen). Andere
  Sensoren (Cooldown/API/Coupon) sind trivial und davon nicht betroffen, daher
  nur dieser eine Sensor auffällig. Jetzt strikt getrennt: Berechnung fehlschlägt
  → Fallback auf 'unknown' + Warnung im Log, POST läuft in jedem Fall.

## [0.57.6] - 2026-07-19

### Fixed
- **sensor.tuiwatch_markttrend wurde in HA immer wieder „nicht verfügbar"** —
  Sensor überlebt (wie alle per States-API gesetzten Sensoren) einen
  HA-Core-Neustart nicht von selbst und verschwindet aus der State Machine,
  bis er neu gepostet wird. Refresh-Intervall von 10 auf 2 Minuten verkürzt
  (wie beim API-Verfügbar- und Coupon-Sensor) — verkleinert das Zeitfenster
  nach einem HA-Neustart deutlich. Bei zu wenigen Datenpunkten war der Status
  schon immer „unknown" (nie „unavailable").

## [0.57.5] - 2026-07-17

### Fixed
- **Zimmerauswahl/Preisprüfung 0 Treffer bei Hotels ohne Transfer-Paket** — die
  Offer-API nutzte seit v0.9.0 `transferIncluded=true` als Default (passend zur
  Buchung auf tui.com), liefert bei Hotels ohne buchbares Transfer-Paket
  (Selbstanreise-Regionen) dafür 0 Treffer, obwohl auf tui.com ganz normal
  buchbare Angebote existieren. Live verifiziert: Hotels MIT Transfer-Paket
  liefern bei `true`/`false` identische Treffer+Preise, nur bei Hotels OHNE
  Transfer-Paket macht es den Unterschied (0 vs. alle). Preisprüfung und
  Zimmerauswahl fallen jetzt automatisch auf `false` zurück, wenn `true` 0
  Treffer liefert — aber nur, solange der Nutzer nichts explizit festgelegt hat.

### Added
- Neuer Schalter „Transfer inklusive" in der Zimmerauswahl eines Angebots —
  fixiert `transferIncluded` fest auf der Angebots-URL (wirkt automatisch auch
  auf die reguläre Preisprüfung), kein automatischer Fallback mehr, sobald
  explizit gesetzt.
- Neuer Filter „Transfer" in der Hotelsuche (links neben „Nur Direktflug",
  Standard an) — echter serverseitiger Filter der Such-API (live verifiziert:
  Hotels ohne Transfer-Paket verschwinden komplett aus der Trefferliste),
  kein Fallback. Verhindert, dass nicht direkt vergleichbare Selbstanreise-
  Angebote die Trefferliste verfälschen.

## [0.57.4] - 2026-07-17

### Added
- Hotelsuche: Feld „Max. Preis p.P." neben Fluggesellschaften — filtert
  Treffer über dem Preis (p.P.) raus. Wird wie Sterne/Weiterempfehlung
  clientseitig nachgefiltert, in gespeicherten Suchen mitgespeichert.

## [0.57.3] - 2026-07-17

### Fixed
- Übersetzung für `calendar_daily_refresh` gefehlt — Einstellung erschien im
  UI als roher Konfigurationsschlüssel statt als Text. Ergänzt in
  `translations/de.yaml` und `translations/en.yaml`.

## [0.57.2] - 2026-07-16

### Fixed
- **Echte Root-Cause des Check24-Timeouts gefunden** — v0.57.1 (60s-Budget) war
  eine Fehldiagnose. Tatsächlich antwortet Check24 bei einem gültigen Hotel
  ohne Angebot für die exakten Termine sofort (<1s) mit `status: "Empty"` —
  ein dritter Terminal-Status neben `Success`/`Error`, den der Poll-Loop nicht
  kannte und deshalb bis zum Timeout weiterlief, obwohl "kein Angebot" längst
  feststand. Live verifiziert (Gloria Palace Amadores, 03.–14.05.2027, ein
  Termin ohne Check24-Angebot): jetzt 1,1s statt 73s.

## [0.57.1] - 2026-07-16

### Fixed
- **Check24-Vergleich lief in echte Timeouts, obwohl das Hotel gültige Angebote
  hatte** — Job/Poll-Budget war 20 Versuche (~30s), Bugreport zeigte aber echte
  Wartezeiten von 38s/42s im Produktivbetrieb (lokal nachgestellt: derselbe
  Job löst sich zuverlässig auf, nur variabel langsamer als beim Live-Test
  angenommen). Budget auf 40 Versuche (~60s) erhöht. Spinner-Text in der UI
  war zudem noch ein Playwright-Ära-Leftover ("kann bis zu einer Minute
  dauern" — stimmte zufällig ungefähr, aber aus dem falschen Grund),
  jetzt realistisch beschriftet.

## [0.57.0] - 2026-07-16

### Added
- **Hotelsuchen-Trefferliste per E-Mail versenden** — neuer "✉ Email"-Button in
  der Suche, sendet eine HTML-Mail mit anklickbaren tui.com-Links. Ist eine
  Auswahl markiert (Checkbox, geteilt mit dem KI-Vergleich), wird nur diese
  versendet, sonst die komplette aktuelle Trefferliste. Neues Modul
  `email_search.py` (statt weiterem Wachstum von app.py) baut die Mail aus den
  bereits geladenen Suchergebnissen, neue Route `POST /api/search/email`. Die
  Auswahl-Checkbox in der Trefferliste ist dafür nicht mehr an das
  KI-Feature-Flag gekoppelt (vorher nur bei aktivierter KI sichtbar).

## [0.56.1] - 2026-07-16

### Added
- **"Egal"-Checkbox für Sterne/Weiterempfehlung in der Hotelsuche** — sperrt
  beide Felder und lässt den Filter komplett weg, statt sie manuell auf 0
  setzen zu müssen. Zustand wird in gespeicherten Suchen mitgesichert.

## [0.56.0] - 2026-07-16

### Added
- **"Mehr laden" in der Hotelsuche** — die Such-API liefert pro Aufruf nur
  50 Treffer (`resultsPerPage`), auch bei viel mehr echten Treffern in der
  Region (z. B. 210). Neuer Button unter der Trefferliste lädt die nächste
  Seite nach (`resultsFrom`/`offset`) und hängt sie an, statt dass die
  restlichen Treffer schlicht nie abgerufen werden.

## [0.55.8] - 2026-07-16

### Fixed
- **"N Treffer in der Region"-Anzeige war bei großen Regionen zu niedrig** —
  `resultsTotal` in der Such-API-Anfrage ist kein reiner Info-Wert, sondern ein
  Cap: die Antwort deckelt ihre eigene (echte) Trefferzahl auf diesen Wert
  (live verifiziert: 300 angefragt bei 703 echten Treffern → Antwort "300").
  Cap von 300 auf 1000 angehoben.

## [0.55.7] - 2026-07-16

### Fixed
- **Hotelsuche zeigte deutlich teurere Hotels als tui.com selbst** — Beispiel:
  Mallorca-Suche zeigte "ab 908 €", tui.com für dieselben Parameter "ab 572 €".
  Ursache: die Such-API wurde mit `sortingOrder: "qualifier2DESC"` (Best-Match-
  Score, nicht Preis) abgefragt und nur die ersten 50 von z. B. 256 Treffern
  geholt (`resultsPerPage`) — die günstigsten Hotels waren dadurch oft gar nicht
  im abgeholten Batch, das clientseitige "Preis aufsteigend"-Sortieren in der
  UI konnte sie folglich nicht finden (sie waren nie in den Daten). Auf
  `sortingOrder: "priceAsc"` umgestellt (live gegen tui.com selbst per
  `sortHotelsField=price&sortHotelsAsc=1` verifiziert — liefert exakt dieselben
  günstigen Hotels).

## [0.55.6] - 2026-07-16

### Fixed
- **Check24-Vergleich meldete "nicht verfügbar" trotz echter Angebote** — der
  serverseitige `cateringList`-Filter (v0.55.4) funktionierte korrekt, aber der
  zusätzliche Client-Filter verglich Textstrings: TUI liefert Verpflegung auf
  Deutsch ("Alles Inklusive"), Check24s `mealType` wurde intern zu "All
  Inclusive" (Englisch) übersetzt — der Substring-Vergleich der beiden matchte
  nie, das Angebot fiel fälschlich unter `no_offers_for_board`. Filter
  vergleicht jetzt stattdessen über dieselben Check24-Tier-Codes wie die
  `cateringList`-Anfrage (sprachunabhängig, funktioniert für alle
  Verpflegungsstufen einheitlich).
- Check24-Cooldown von 120s auf 30s reduziert — war ein Playwright-Ära-Wert
  (Browser-Start + Anti-Bot-Vorsicht), seit v0.55.5 (reines `requests`,
  ~8-15s Laufzeit) nicht mehr nötig.

## [0.55.5] - 2026-07-16

### Changed
- **Check24-Vergleich läuft nicht mehr über Playwright, sondern über ein
  offenes JSON-API** — Annahme aus v0.54.0 war falsch: das `cryptString`-Feld
  in `/suche/json/dynamic/offer` ist nur ein Buchungs-/Verfügbarkeits-Token,
  nicht die verschlüsselte Preis-Nutzlast. Preis, Zimmer, Verpflegung,
  Veranstalter stehen im selben JSON bereits im Klartext. `check24_client.py`
  nutzt jetzt reines `requests` (Job/Poll-POST) statt Headless-Chromium —
  schneller (~8-15s statt fixer 12s-Wartezeit + Browser-Start), robuster
  (kein Container-/Chromium-Build-abhängiges Verhalten mehr, siehe die
  `page.fill()`-vs-`page.type()`-Fixes in v0.54.2), kein Anti-Bot-Risiko durch
  Headless-Browser-Fingerprinting mehr. Auch die Hotelsuche
  (`search_hotel()`) läuft jetzt über ein offenes JSON-API
  (`/autocompleter-destination`) statt simuliertem Autocomplete-Tippen.
  Rückgabeformat/Verhalten unverändert, keine Auswirkung auf App/Routen.
  Details: SCRAPING_CHECK24.md.

## [0.55.4] - 2026-07-16

### Fixed
- **Check24-Vergleich ignorierte die Verpflegung** — bei TUI-Angebot "All
  Inclusive" wurden ungefiltert auch deutlich günstigere Halbpension-Angebote
  gezeigt (Preisvergleich dadurch irreführend). Check24 hat auf der
  Angebotsseite selbst einen Verpflegungs-Filter (Tabs "Mind. Frühstück" /
  "Mind. Halbpension" / "Mind. Vollpension" / "All Inclusive"), der über den
  Query-Param `cateringList=<stufe-oder-besser>` steuerbar ist — live per
  Playwright ermittelt (Klick auf den Tab beobachtet, siehe
  SCRAPING_CHECK24.md). `check24_client.fetch_offers()` setzt diesen Param
  jetzt passend zur TUI-Verpflegung direkt beim Laden, der bisherige weiche
  Textfilter fällt bei fehlendem Treffer nicht mehr auf "ungefiltert zeigen"
  zurück (das war die Ursache der falschen Daten).

## [0.55.3] - 2026-07-16

### Fixed
- Gestrichelte Unterlinie am Preis (Check24-Klickhinweis) kollidierte optisch mit
  der Durchstreichung bei reduzierten Preisen — entfernt, nur noch Cursor/Hover.

## [0.55.2] - 2026-07-16

### Fixed
- **Check24-Vergleich fragte falsche Reisedaten ab** — nutzte `startDate`/`endDate`
  aus der TUI-URL, das ist aber das (ggf. mehrmonatige) Such-Zeitfenster der
  Flex-Suche, nicht das tatsächlich gebuchte Datum. Beispiel: echtes Angebot
  7 Nächte ab 06.12.2026, Check24-Abfrage lief aber mit 20.07.2026–17.10.2027.
  Jetzt werden Abreisedatum aus `details` ("... Nächte ab DD.MM.YYYY") und
  Rückreisedatum/Abflughafen aus den bereits gespeicherten, echten Angebotsfeldern
  (`return_date`, `dep_airport`) genutzt.

### Changed
- **Check24-Vergleich per Klick auf den Preis statt eigenem Button** — der
  "Check24 verknüpfen"/"Check24-Vergleich"-Button in der Aktionsleiste entfällt;
  ein Klick auf den Preis (nur bei aktivem Feature) startet direkt die Verknüpfung
  bzw. den Vergleich.

## [0.55.1] - 2026-07-15

### Fixed
- **Angebote mit Verpflegungsfilter "Frühstück" (`boardTypes=BB`) fälschlich als
  "nicht verfügbar" gemeldet** — betraf Preis-Abruf, Preiskalender ("0 Tage") und
  Zimmerauswahl ("keine Zimmer gefunden") gleichermaßen, obwohl das Angebot auf
  tui.com verfügbar war. Ursache: die Angebots-/Kalender-API nutzt intern `BR`
  statt `BB` als Code für Frühstück (`GT06-BB` lieferte an 3 unabhängig
  getesteten Hotels durchweg 0 Treffer, `GT06-BR` die echten Angebote) —
  `AI`/`HB`/`FB`/`AO` sind davon nicht betroffen und bleiben unverändert.

## [0.55.0] - 2026-07-15

### Added
- **Check24-Vergleich zeigt jetzt den Reiseveranstalter** je Zeile (z. B. "ITS
  Dynamisch", "DERTOUR Dynamisch", "alltours dynamisch") statt nur Zimmer/
  Verpflegung/Preis — Anbietername steht im `alt`-Text des Anbieter-Logos je
  Angebotskarte.
- **Link "Auf Check24 ansehen"** im Ergebnis — führt direkt zur Check24-
  Angebotsseite für das verknüpfte Hotel/die Reisedaten (kein Deep-Link auf
  die exakte Zeile möglich, "zur Buchung" ist reine JS-Navigation ohne
  statischen Link).

## [0.54.3] - 2026-07-15

### Fixed
- **Check24-Vergleich zeigte absurd niedrige Preise** (z. B. "3,34 €" statt des
  echten Zimmerpreises). Ursache: jede Angebotskarte enthält neben dem echten
  Preis auch eine Smily-Punkte-Zeile im selben Format ("2,54 € als Smily Punkte
  sammeln") — die Preis-Regex nahm den *letzten* Treffer im Kartentext, das war
  die Punktezahl, nicht der Preis. Regex schließt Smily-Punkte-Treffer jetzt
  gezielt aus.

## [0.54.2] - 2026-07-15

### Fixed
- **CI-Bruch in v0.54.1**: `check24_client.search_hotel()` importierte `playwright`
  vor dem Leer-Anfrage-Check statt danach — brach den reinen Parsing-Test in CI
  (dort ist playwright absichtlich nicht installiert) und war strukturell falsch
  gegenüber dem lazy-import-Muster aus `scraper.py`.
- **Check24-Hotelsuche fand im Add-on-Container nie einen Treffer** (0 Treffer,
  ohne Fehler im Log) — im lokalen Test mit Playwrights eigenem Chromium
  funktionierte dieselbe Suche zuverlässig. Ursache: `page.fill()` setzt den
  Feldwert nur per `input`/`change`-Event; das jQuery-UI-Autocomplete-Widget auf
  Check24 hört dafür offenbar auf echte Tastatur-Events — mit dem System-
  Chromium im Container (`CHROMIUM_PATH`) blieb das folgenlos. Jetzt `page.type()`
  (simuliert echte Tastendrücke) statt `page.fill()`. Zusätzlich: 0-Treffer wird
  jetzt immer geloggt (nicht nur bei `verbose_log`), inkl. Anzahl roher
  Autocomplete-Elemente — damit ein erneutes Auftreten diagnostizierbar bleibt.

## [0.54.1] - 2026-07-15

### Changed
- **Check24-Hotel automatisch statt Link einfügen.** Der "Check24 verknüpfen"-
  Button verlangte bisher, einen kompletten Check24-Hotel-Link von Hand zu
  suchen und einzufügen — zu umständlich für einen Preisvergleich. Jetzt
  durchsucht TUIWatch Check24 automatisch mit dem bereits bekannten
  TUI-Hotelnamen (Check24s eigenes Zielsuchfeld, kein Tippen nötig); bei
  eindeutigem Treffer wird sofort verknüpft und der Vergleich gestartet, bei
  mehreren ähnlichen Hotels erscheint eine kurze Klick-Liste. Der manuelle
  Link bleibt als Fallback (`PATCH .../check24_link`), falls die Suche ein
  Hotel nicht findet. Nebenbei vereinfacht: `areaId` war gar nicht nötig
  (`hotelId` allein reicht, Check24 leitet automatisch weiter) — der bisherige
  Zwischenschritt über die Hotel-Ergebnisliste (inkl. Popup-Klick) entfällt.

## [0.54.0] - 2026-07-15

### Added
- **Check24-Preisvergleich (Beta, `enable_check24_compare`)**: ein Angebot kann
  einmalig mit einem Check24-Hotel verknüpft werden (Link von
  urlaub.check24.de/suche/hotel…), danach zeigt "Check24-Vergleich" den
  günstigsten passenden Preis anderer Reiseveranstalter (gleiche Reisedaten,
  ähnliche Zimmerkategorie/Verpflegung) neben dem TUI-Preis — nach demselben
  Muster wie Pro-Person-Vergleich (Hintergrund-Abruf, gespeichertes Ergebnis,
  "Neu abfragen"). Standardmäßig deaktiviert (Check24 hat kein offenes API,
  Abruf läuft über Headless-Chromium und ist entsprechend langsamer/fragiler
  als der TUI-Abruf — siehe SCRAPING_CHECK24.md). Verpflegung (`board`) wird
  dafür jetzt auch strukturiert je Angebot gespeichert, nicht nur als Text in
  den Details.

## [0.53.6] - 2026-07-14

### Added
- **GIATA-Fotogalerie: Lightbox statt neuer Tab.** Klick auf ein Thumbnail
  zeigt das Foto jetzt in Originalgröße direkt im Modal (size=800 statt
  600), statt einen neuen Browser-Tab zu öffnen.

## [0.53.5] - 2026-07-14

### Changed
- **GIATA-Fotogalerie: Hinweistext entfernt.** Untertitel im Modal
  ("Bilder von der öffentlichen GIATA-Hotelseite …") gestrichen.

## [0.53.4] - 2026-07-14

### Fixed
- **GIATA-Fotogalerie: nur 7 statt aller Bilder.** Die GIATA-Hotelseite
  listet Kataloge, nicht Fotos, und ist ab ~30 Katalogen paginiert
  (`&site=2..N`) — bisher wurde nur Seite 1 gelesen. Jetzt werden bis zu
  8 Seiten durchlaufen; ein Hotel mit 180 Katalogeinträgen zeigte dadurch
  vorher nur 7, jetzt 23 echte Fotos.

## [0.53.3] - 2026-07-14

### Fixed
- **Ungewollter Logout trotz aktiver Nutzung.** Die Login-Session lief bisher
  exakt `session_hours` (Standard 24h) nach dem Login ab, unabhängig von der
  Nutzung — bei durchgehend offenem Tab kam irgendwann unerwartet der
  Login-Screen (z. B. beim Reload). Jetzt sliding: jede Anfrage verlängert
  Session + Cookie neu; nur wirklich inaktive Sessions (>24h ohne Zugriff)
  laufen noch ab. (Betrifft nur den direkten Zugriff, nicht HA Ingress.)

## [0.53.2] - 2026-07-14

### Fixed
- **GIATA-Fotogalerie: fehlgeschlagener Abruf ohne Log-Eintrag.** Netzwerk-
  Fehler und leere Ergebnisse beim Laden der GIATA-Seite wurden bisher still
  verschluckt. Jetzt landet eine Warnung im ⚠-Panel/Log.

## [0.53.1] - 2026-07-14

### Fixed
- **GIATA-Fotogalerie: doppelte Bilder.** Dedupe lief bisher über `cid`+`iid`,
  aber dasselbe Foto taucht unter mehreren Katalogen (`cid`) mit gleicher
  Bild-ID (`iid`) erneut auf. Jetzt wird nur noch nach `iid` dedupliziert.

## [0.53.0] - 2026-07-14

### Fixed
- **CodeQL: Polynomial-Regex bei GIATA-Bildparsing** (`scraper.py`) —
  `cid`/`iid` werden jetzt per `urllib.parse.parse_qs` statt Regex mit `.*?`
  aus der Bild-URL gelesen (kein ReDoS-Risiko auf externen Response-Daten).

## [0.52.12] - 2026-07-14

### Added
- **🖼 Fotos-Galerie (GIATA).** Neuer Link neben dem GIATA-Code öffnet eine
  Galerie mit Hotelfotos von der öffentlichen GIATA-Hotelseite — Bilder werden
  direkt eingebettet (i.giatamedia.com), nicht heruntergeladen oder gespeichert.

## [0.52.11] - 2026-07-14

### Added
- **GIATA-Code als Link.** "GIATA <code>" bei Angeboten (Anzeige + E-Mail)
  verlinkt jetzt auf die GIATA-Hoteldetailseite (hg15.giatamedia.com).

## [0.52.10] - 2026-07-14

### Added
- **TripPilot: Regionen Kanaren, Mittelmeer, Karibik, Südostasien und
  Indischer Ozean** bei "Wohin soll die Reise ungefähr gehen?" ergänzt.

## [0.52.9] - 2026-07-14

### Added
- **Logout-Button im Header.** Neben dem Design-Umschalter (nur sichtbar,
  wenn nicht über HA Ingress aufgerufen, da Ingress selbst authentifiziert).

## [0.52.8] - 2026-07-13

### Fixed
- **TripPilot: KI-Name im Ladetext fehlte manchmal** ("KI sucht passende
  Ziele…" statt z. B. "Claude sucht…"). Ursache: Race Condition beim
  Seitenaufruf, bei der der aktive Provider noch nicht geladen war. Wird
  jetzt vor dem Absenden sichergestellt.

### Added
- **TripPilot: Temperaturoption "20–30°C" ergänzt**, als breitere Wahl
  zwischen den bestehenden Stufen 20–25°C und 25–30°C.

## [0.52.7] - 2026-07-13

### Added
- **TripPilot: "Starker Wellengang" als Option** bei "Was nervt dich im
  Urlaub?" ergänzt.

## [0.52.6] - 2026-07-13

### Added
- **KI-Prompt vor dem Senden anzeigen.** Neue Option `ai_prompt_preview`
  (Standard aus): ist sie aktiv, zeigt jede interaktive KI-Anfrage (KI-Fazit,
  Vergleich, Buchungsscore, Kalender-Analyse, Region-Ausblick, Portfolio-Frage,
  TripPilot/Tagesausflug, Verlauf-Wiederholen, Folgefrage) den fertigen Prompt zuerst in
  einem editierbaren Fenster — erst nach Bestätigung (ggf. mit Anpassungen)
  geht die Anfrage wirklich an die KI raus. Automatische Hintergrund-Läufe
  (Wochenüberblick, Aktionscode-Check, Auto-Tags) sind davon nicht betroffen.

## [0.52.5] - 2026-07-12

### Fixed
- **Vorjahresvergleich im Buchungsscore (0.52.3) wurde von der KI live falsch
  interpretiert** — sie erwartete eine taggenaue Übereinstimmung mit dem Vorjahr
  und senkte 'vertrauen', weil die (bewusst nur monatsbezogene) Vergleichsbasis
  keine Daten für exakt denselben Kalendertag lieferte. Anweisung klargestellt:
  der Vergleich ist Ø-Preis auf Monatsebene, keine taggenaue Übereinstimmung
  erwartet/nötig, zählt weiterhin voll als typ='daten'.

## [0.52.4] - 2026-07-12

### Added
- **Preis-Leistungs-Score in der Hotelsuche** — neue Sortieroption „Preis-Leistung":
  60 % Weiterempfehlung (HolidayCheck) + 40 % Preis/Nacht, beide auf min/max der
  aktuellen Trefferliste normiert. Weiterempfehlung mit weniger als 15 Bewertungen
  wird zur Basislinie (70 %) gedämpft, sonst verzerrt ein einzelnes 5-Sterne-Review
  den Score. Feste Gewichtung, kein Regler.
- Preis pro Nacht in der Hotelsuche sichtbar (unter dem Streichpreis, wie bereits
  bei den Angebotskarten in 0.52.2).

## [0.52.3] - 2026-07-12

### Added
- **Vorjahresvergleich im Buchungsscore.** Bei langer Vorlaufzeit (z. B. Zieltermin
  September 2027) deckt der abgerufene Preiskalender bereits heute bis weit über
  den Zieltermin hinaus ab — der gleiche Reisemonat ein Jahr früher (September
  2026) liegt dann oft schon mit im Fenster und damit deutlich näher am eigenen
  Abflug. Dieser Vergleich floss bisher nicht in den Score ein; die KI bekommt ihn
  jetzt als eigenes Signal (ähnlich stark gewichtet wie der eigene Preistrend). Die
  Anweisung warnt die KI ausdrücklich davor, die volle Abweichung als reines
  Nachfragesignal zu werten: allgemeine jährliche Preissteigerung und der
  Frühbucher-Effekt (Vorjahresmonat liegt näher am Abflug) erklären einen Teil davon
  bereits selbst. Bei ungewöhnlich großer Abweichung soll sie per Websuche nach
  politischen/wirtschaftlichen Ereignissen am Reiseziel suchen, die das erklären
  könnten.

### Fixed
- `APP_VERSION`-Konstante war seit mehreren Releases nicht mehr mit
  `config.yaml`/version synchron (0.51.3 vs. zuletzt 0.52.2) — Testsuite deckte
  es erst jetzt auf (`test_version_consistency`). Nachgezogen.

## [0.52.2] - 2026-07-12

### Added
- **Preis pro Nacht auf der Angebotskarte** — unter dem Streichpreis, sofern die
  Nächte-Anzahl aus dem Angebotstext erkennbar ist (führt kein eigenes DB-Feld
  ein, nutzt den vom Scraper bereits geschriebenen `details`-Text).

## [0.52.1] - 2026-07-12

### Fixed
- **Reisen-Zusammenfassung: E-Mail-Fenster lag hinter dem Zusammenfassungs-Modal.**
  Alle `.modal-bg` teilen sich denselben `z-index`, Stapelreihenfolge kam bisher
  nur aus der DOM-Position — `email-bg` steht vor `trips-summary-bg` im Markup
  und landete deshalb dahinter. Jetzt bekommt das E-Mail-Fenster beim Öffnen
  einen höheren `z-index`.
- Der Link „Zusammenfassung zukünftiger Reisen" stand inline im Fließtext und
  konnte mitten im Icon umbrechen — jetzt eigene Zeile.
- Kartentitel zeigte den DB-„title" (Ort + Reisejahr, z. B. „Kolymbia 2026") —
  jetzt nur der Ortsname, das Datum steht ohnehin direkt daneben.

### Added
- Hotelname in der Reisen-Zusammenfassung (Text, E-Mail und Modal-Ansicht).

## [0.52.0] - 2026-07-12

### Added
- **Zusammenfassung zukünftiger Reisen** in „Meine Reisen": listet alle
  bevorstehenden Reisen mit Datum + Wochentag, Reisezeitraum und vollen
  Flugdaten (Hin-/Rückflug: Strecke, Zeiten, Flugnummer). Zum Teilen (Web
  Share API, Zwischenablage-Fallback) und per E-Mail-Versand (neue Endpunkte
  `GET /api/trips/summary`, `POST /api/trips/summary/email`).

## [0.51.6] - 2026-07-11

### Fixed
- **Reiseziel-Drilldown (`/api/destinations`) crashte mit
  `AttributeError: module '__main__' has no attribute '_dest_cache'`.**
  Dritter Fund derselben Bugklasse (siehe 0.51.4/0.51.5): `_dest_cache` lag
  nur in `ai_routes.py`, fehlte im Re-Export nach `app.py`. Ergänzt. Alle
  `A.`-Zugriffe in `offers_routes.py` einmal komplett gegen `app.py` geprüft
  — keine weiteren Lücken gefunden.

## [0.51.5] - 2026-07-11

### Fixed
- **Flughafenauswahl (`/api/airports`) crashte mit
  `NameError: name '_airports_cache' is not defined`.** Gleicher Bug wie beim
  Adressbuch-Fix eben, andere Ausprägung: `offers_routes.py` deklarierte
  `global _airports_cache`, obwohl das Modul-Attribut nie in `offers_routes.py`
  selbst existiert — es steckt nur in `ai_routes.py`. Fix: auf
  `A._airports_cache` umgestellt (gleiches Muster wie `_contacts_cache`) und
  in `app.py` neben den übrigen `ai_routes`-Re-Exports ergänzt.

## [0.51.4] - 2026-07-11

### Fixed
- **Nextcloud-Adressbuch (`/api/contacts`) crashte mit
  `AttributeError: module '__main__' has no attribute '_contacts_cache'`.**
  `_contacts_cache` ist in `ai_routes.py` definiert, wurde aber — anders als
  alle anderen `ai_routes`-Symbole — nie nach `app.py` re-exportiert.
  `offers_routes.py` greift per `import app as A` auf `A._contacts_cache` zu,
  fand das Attribut also nie. Fix: `_contacts_cache = ai_routes._contacts_cache`
  neben den übrigen Re-Exports in `app.py` ergänzt.

## [0.51.3] - 2026-07-11

### Fixed
- **Footer-Buttons nach langen Toast-Meldungen unklickbar — echte Ursache
  gefunden.** Der 0.51.2-Fix (Backup-Download nicht mehr an den DOM hängen)
  war eine Fehlspur. Tatsächliche Ursache: `.toast` hatte kein
  `pointer-events:none`. `opacity:0` macht das Element nur unsichtbar, blockt
  aber weiterhin Klicks — und die Box behält die Breite des zuletzt gesetzten
  Texts (`textContent` wird nach dem Ausblenden nie zurückgesetzt). Nach
  Backup/Restore (lange Meldungen wie „Wiederhergestellt: 9 Angebote, 12
  Reisen…") deckte das unsichtbare, zentrierte `position:fixed`-Div einen
  breiten Streifen am unteren Bildschirmrand ab und schluckte dort Klicks
  (u. a. „Perplexity aktiv"/„⚙ KI-Prompts" im Footer) — bis zum nächsten
  Neuladen, wodurch `textContent` wieder leer wurde und die Box schrumpfte.
  `.toast` hat jetzt durchgängig `pointer-events:none`.

## [0.51.2] - 2026-07-11

### Fixed
- **Footer-Buttons nach Backup/Restore manchmal nicht klickbar (Verdacht).**
  Nach „⬇ Backup" oder „⬆ Restore" blieb z. B. der Provider-Umschalter im Footer
  gelegentlich unklickbar (Hover-Cursor blieb Pfeil statt Hand) — behoben erst
  durch Neuladen der Seite. Ursache: bekannte Chromium-Eigenart, bei der ein
  synthetischer `<a>`-Klick (Download auslösen) inkl. DOM-Insert/Remove das
  `:hover`-Tracking der Seite durcheinanderbringen kann. `backupOffers()` hängt
  den Download-Link jetzt nicht mehr in den DOM — behebt den Fall vermutlich für
  „⬇ Backup". Für „⬆ Restore" (echter nativer Datei-Dialog, zwingend im DOM
  nötig) gibt es keinen Code-Workaround; falls der Glitch dort weiter auftritt,
  ist das reines Browser-Verhalten nach dem OS-Dialog, kein TUIWatch-Bug.

## [0.51.1] - 2026-07-11

### Fixed
- **Ursprüngliche Antwort ging beim erneuten Öffnen aus dem KI-Verlauf verloren.**
  Nach einer Folgefrage zeigte das Wiederöffnen eines Verlaufseintrags nur noch
  die letzte Antwort (`summary`-Spalte), die komplette gespeicherte Konversation
  (`conversation`-Spalte) wurde ignoriert. `renderAiResult` rekonstruiert die
  sichtbare Konversation jetzt aus `conversation`, falls vorhanden — Original-
  fazit und alle Folgefragen/-antworten bleiben beim Wiederöffnen sichtbar.

## [0.51.0] - 2026-07-11

### Added
- **Folgefragen zu KI-Ergebnissen.** Unter jedem Freitext-Ergebnis (KI-Fazit,
  Vergleich, TripPilot, Kalenderanalyse, Frag dein Portfolio) — auch nachträglich
  beim erneuten Öffnen aus dem KI-Verlauf — lässt sich jetzt eine Folgefrage
  stellen: echte Mehrfach-Turn-Konversation (bisheriger Prompt + Antwort + neue
  Frage), nicht nur derselbe Prompt erneut wie bei „🔁 Wiederholen". Läuft mit
  demselben Modell/Provider weiter, das die Erstantwort gegeben hat, und
  funktioniert bei allen 3 Anbietern (Claude/Gemini/Perplexity unterstützen alle
  Konversationen). Neuer Endpoint `POST /api/ai/history/<id>/followup`, neue
  DB-Spalte `ai_analyses.conversation` (Backup/Restore-fähig). Nicht verfügbar
  bei Buchungsscore/Region-Ausblick (strukturiertes JSON).

## [0.50.0] - 2026-07-11

### Added
- **Ladetexte nennen den aktiven KI-Anbieter beim Namen.** „KI durchsucht das
  Web…" hieß bisher immer nur „KI", egal ob Claude, Gemini oder Perplexity
  gerade lief. Alle Lade-/Fortschrittstexte (Buchungsscore, KI-Fazit,
  Vergleich, TripPilot, Kalenderanalyse, Frag dein Portfolio, PDF-Vorschläge,
  Auto-Tags, Verlauf-Wiederholen) zeigen jetzt den echten Namen.

## [0.49.5] - 2026-07-11

### Added
- **Perplexity-Quellenangaben anklickbar.** Zitat-Marker wie `[1][5]` in
  Perplexity-Antworten waren bisher toter Text. Werden jetzt serverseitig gegen
  die zugehörigen URLs aus `search_results`/`citations` zu Markdown-Links
  aufgelöst (`[1](https://…)`) und im Frontend (Web-UI + PDF-Export + E-Mail)
  als klickbare, hochgestellte Zahl gerendert (`.ai-cite`). Betrifft nur
  Perplexity — Claude/Gemini liefern Quellen bereits anders.

## [0.49.4] - 2026-07-11

### Fixed
- **Perplexity-Kostenschätzung berücksichtigt jetzt die Request-Gebühr.** Anfragen
  pinnen `search_context_size: "low"` (statt dem API-Default zu überlassen) —
  macht die zusätzliche, gestaffelte Request-Gebühr planbar UND die Kostenanzeige
  rechnet sie jetzt mit ein (bisher nur reine Tokenkosten, Gebühr fehlte
  komplett). Schätzung liegt damit nah an den echten Kosten statt sie
  systematisch zu unterschätzen.

## [0.49.3] - 2026-07-11

### Added
- **Perplexity als dritter KI-Anbieter.** Sonar-Modelle (`sonar`, `sonar-pro`,
  `sonar-reasoning-pro`, `sonar-deep-research`) stehen jetzt gleichberechtigt neben
  Claude und Gemini zur Verfügung — neue Optionen `perplexity_api_key`/
  `perplexity_model`. Der Provider-Umschalter (Footer + „🔁 Wiederholen" im
  KI-Verlauf) unterstützt jetzt bis zu 3 konfigurierte Anbieter statt nur 2
  (`/api/ai/provider` liefert neu `configured_providers`, `both_configured`
  bedeutet jetzt „mind. 2 von 3 konfiguriert"). Perplexity durchsucht bei jeder
  Anfrage automatisch das Web (kein Websuche-Schalter, `ai_max_web_searches`
  greift hier nicht) und ist pro Aufruf teurer als Claude/Gemini — Preis-Schätzung
  in der KI-Kostenanzeige berücksichtigt nur die Tokenkosten, nicht die
  zusätzliche Perplexity-Request-Gebühr.

## [0.49.2] - 2026-07-10

### Added
- **Markttrend: Daten pro Destination löschbar.** Neuer 🗑-Button je Region im
  Markttrend-Modal (mit Rückfrage): löscht die gesammelten Datenpunkte NUR dieser
  Destination und beginnt die Aufzeichnung dort neu — andere Regionen bleiben
  unberührt (`DELETE /api/market-trend/region`). Hinweis: „Neu berechnen" baut
  alle Regionen aus dem Preisverlauf wieder auf.

## [0.49.1] - 2026-07-10

### Added
- **✕ zum Leeren in allen Suchfeldern.** Hauptsuche, KI-Verlauf-Suche,
  Reiseziel-Picker & Co. zeigen bei Eingabe ein ✕ am Feldende — Klick leert das
  Feld und aktualisiert die Liste sofort. Greift generisch für jedes (auch
  künftige) Suchfeld mit „Suchen…"-Placeholder.

## [0.49.0] - 2026-07-10

### Added
- **Preiskalender wird täglich automatisch aufgefrischt.** Der Poller holt 1×/Tag
  je aktivem Angebot den Kalender neu (max. 10 je Zyklus, älteste zuerst, je ~3
  API-Calls) — `calendar_history` wird dichter, Trend-Ansicht und das
  Kalender-Bewegungs-Signal im Buchungsscore (0.46.4) werden aussagekräftiger.
  Ergänzt den Sofort-Refresh bei Preisänderung; abschaltbar über die neue Option
  `calendar_daily_refresh`.
- **Buchungsscore-Verlauf.** Jeder frisch berechnete Score wird mit dem Angebot
  verknüpft gespeichert (neue Spalte `offer_id` in `ai_analyses`); das
  Score-Modal zeigt ab der zweiten Messung „Verlauf: 72 → 65 (−7)" plus
  Mini-Sparkline (Tooltip mit allen Messungen). Ältere Einträge (vor 0.49.0)
  haben keine Verknüpfung und tauchen im Verlauf nicht auf.

## [0.48.8] - 2026-07-10

### Fixed
- **🔔 Meldungen-Panel: Telegram-Texte lesbar.** Nachrichten zeigten die rohen
  Bot-HTML-Tags (`<b>…</b>`) und URLs als toten Fließtext. Jetzt: Whitelist-Tags
  (fett/kursiv/code) werden gerendert, Links sind klickbar und werden gekürzt
  angezeigt.
- **Fehlalarm „Kaputtes JSON in DB-Feld ignoriert … NoneType" beseitigt.** Trat
  bei jedem Packlisten-Zugriff auf, wenn keine eigene Vorlage gesetzt war —
  `None` (= keine Vorlage, Normalfall) lief fälschlich durch den
  Korruptions-Warner. Standard-Vorlage war nie beeinträchtigt.

## [0.48.7] - 2026-07-10

### Changed
- **Modularisierung abgeschlossen (Backlog #12):** Frontend-JS (~3.280 Zeilen)
  aus `templates/index.html` nach `static/app.js` ausgelagert — im Template
  bleibt nur der kleine Jinja-Block (Ingress-Base, Intervall, KI-Flag,
  Heimatort) + `<script src=…?v=APP_VERSION>` (Cache-Busting pro Version;
  Service worker ist network-first, keine Stale-Gefahr). index.html damit
  von ~4.200 auf ~930 Zeilen. Wizard-Test liest ADV_STEPS jetzt aus app.js.
  Live verifiziert (Seite lädt, app.js 200, Ingress-Base im Inline-Block).

## [0.48.6] - 2026-07-10

### Changed
- **Modularisierung Tranche 3 (Backlog #12):** `ai_routes.py` (KI-Analyse:
  Prompts, Usage/Kosten, KI-Verlauf, alle /api/ai-Routen — 1.514 Zeilen) und
  `offers_routes.py` (Angebots-CRUD, Verlauf, Vergleiche, Hotelsuche,
  Reiseziele, Zimmer — 768 Zeilen) ausgelagert. app.py damit bei ~2.800 Zeilen
  (Start: ~7.400, −62 %). Keine Verhaltensänderung, 308 Tests grün.

## [0.48.5] - 2026-07-10

### Changed
- **Modularisierung Tranche 2 abgeschlossen (Backlog #12):** `watch.py` (Suchabo:
  Prüf-Logik + /api/searches-Routen, 232 Zeilen) ausgelagert — app.py damit bei
  ~4.900 Zeilen (Start: ~7.400). Keine Verhaltensänderung, 308 Tests grün.

## [0.48.4] - 2026-07-10

### Changed
- **Modularisierung Tranche 2 (Backlog #12):** `ai_client.py` (KI-Provider-Client
  Anthropic/Gemini, 184 Zeilen) und `price_calendar.py` (Preiskalender:
  Snapshot/Trend/Bewegungen + /api/calendar-Routen, 279 Zeilen) aus app.py
  ausgelagert — gleiches A.-Muster wie Tranche 1, keine Verhaltensänderung,
  308 Tests grün. Dockerfile-COPY jeweils ergänzt (Guard-Test schlug korrekt an).

## [0.48.3] - 2026-07-10

### Fixed
- **0.48.2 startete weiterhin nicht (Zirkular-Import-Crash).** Zweite Folge der
  Modularisierung: run.sh startet `python3 app.py` — das Modul heißt dann
  `__main__`, und `import app` in den Blueprint-Modulen führte app.py ein
  ZWEITES Mal aus → `AttributeError: partially initialized module`. Unter
  pytest unsichtbar, weil dort app als Modul `app` importiert wird. Fix:
  `sys.modules['app']`-Alias vor dem Blueprint-Import — `__main__` und `app`
  sind damit dasselbe Modul-Objekt. Dazu zweiter Guard-Test
  (`tests/test_script_start.py`): startet app.py als echten Skript-Subprozess
  wie im Add-on und wartet auf `/health` — fängt jede künftige Start-Regression,
  die nur im Skript-Modus auftritt.

## [0.48.2] - 2026-07-10

### Fixed
- **0.48.1 startete nicht (Crash-Loop `ModuleNotFoundError: trips_routes`).**
  Die Modularisierung legte neue Python-Module an, das Dockerfile kopiert aber
  eine feste Dateiliste ins Image — die neuen Dateien fehlten. COPY-Zeile
  ergänzt. Dazu ein Guard-Test (`tests/test_dockerfile.py`): jede von app.py
  (direkt/transitiv) importierte lokale Python-Datei muss im Dockerfile
  auftauchen — der Fehler wäre damit VOR dem Push rot gewesen, obwohl alle
  Funktionstests grün waren.

## [0.48.1] - 2026-07-10

### Changed
- **Wartbarkeit: app.py modularisiert (Backlog #12, erste Tranche).** Drei
  zusammenhängende Blöcke (~1.600 Zeilen, ~25 %) in eigene Module verschoben —
  reine Umstrukturierung, keine Verhaltensänderung, alle 306 Tests unverändert:
  - `trips_routes.py`: alle Reisen-Routen (Import/Rescan/Feld-Zuordnung/Debug/
    Anhänge/Packliste/Vorlage) als Flask-Blueprint
  - `backup_routes.py`: Backup/Restore inkl. automatischem Wochen-Backup
  - `digest.py`: Wochen-Digest (Aufbau + Versand)
  - Muster: Module greifen per `import app as A` spät auf geteilte Primitiven
    zu — kein Import-Zyklus, Test-Monkeypatches bleiben wirksam. Weitere
    Tranchen (Kalender, KI-Client, JS aus index.html) folgen bei Bedarf.

## [0.48.0] - 2026-07-10

### Added
- **🔔 Meldungen & Fehler im UI** (Footer-Link): zwei neue Ansichten, die das
  Wühlen im HA-Log ersetzen.
  - *Benachrichtigungen*: Verlauf aller gesendeten HA-/Telegram-Meldungen
    (Zeitpunkt, Kanal, Text, gesendet/fehlgeschlagen) — dauerhaft in der DB,
    letzte 500 (`notify_log`, `GET /api/notifications`).
  - *Warnungen/Fehler*: die letzten 100 WARNING/ERROR-Einträge seit Add-on-Start
    aus einem eigenen Puffer (der INFO-lastige Konsolen-Puffer rotiert sie sonst
    schnell raus) — `GET /api/errors`.
- **🤖 KI-Vorschläge in der manuellen Feld-Zuordnung**: neuer Button im
  Debug-Editor — die KI liest das gespeicherte PDF und füllt Vorschläge in die
  leeren Eingabefelder (gleiches Schema wie der Import-Fallback). Nichts wird
  automatisch gespeichert: prüfen, dann „💾 Zuordnung speichern"
  (`POST /api/trips/<id>/fields/suggest`).

### Fixed
- **Backup-Lücke: Packlisten-Vorlage.** Die eigene Packlisten-Vorlage (0.47.2)
  wird jetzt im Backup mitgesichert und beim Restore wiederhergestellt (wie die
  KI-Prompt-Vorlagen; nicht-destruktiv, überschreibt nichts Vorhandenes).

## [0.47.2] - 2026-07-10

### Added
- **Packlisten-Vorlage editierbar.** Neuer Button „📝 Vorlage" im Packlisten-Kopf:
  die Vorlage, aus der neue Packlisten erzeugt werden, lässt sich jetzt selbst
  anpassen (einfaches Textformat: `# Kategorie` als Überschrift, darunter je Zeile
  ein Item, max. 70 gesamt). Die angepasste Vorlage gilt für Packlisten neuer
  Reisen und beim „↺ Zurücksetzen"; bestehende Reise-Packlisten bleiben unverändert.
  „Standard-Vorlage wiederherstellen" bringt die eingebaute Vorlage zurück
  (GET/POST `/api/packing-template`).

## [0.47.1] - 2026-07-10

### Added
- **Manuelle Zuordnung: Rabatte + „Rabatt bereits im Reisepreis enthalten".**
  Die Rabatt-Liste (Code + Betrag) lässt sich jetzt wie die Extras manuell
  festlegen (Beträge werden automatisch negativ normalisiert, „150" → „−150,00").
  Neu dazu ein Schalter für die zwei TUI-PDF-Varianten: standardmäßig wird der
  Rabatt zum Brutto-Paketpreis zurückgerechnet (Rabatt im Gesamtpreis verrechnet);
  ist „Rabatt bereits im Reisepreis enthalten" gesetzt, entfällt die Rückrechnung —
  der Rabatt ist dann nur informativ ausgewiesen. Die Detailansicht kennzeichnet
  diesen Fall bei den Rabatten.

## [0.47.0] - 2026-07-10

### Added
- **Meine Reisen: Felder manuell zuordnen (Debug-Ansicht).** Wenn der PDF-Parser
  nach einer TUI-Layout-Änderung Felder nicht erkennt, lassen sie sich jetzt selbst
  setzen: Text im bereinigten PDF-Auszug markieren und per „⇦ Auswahl" übernehmen —
  oder direkt eintippen. Unterstützt alle Kernfelder (Buchungsnummer/-datum,
  Reiseziel, Hotel, An-/Abreise, Nächte, Verpflegung, Gesamtpreis, Reisende-Anzahl,
  Anzahlung/Restzahlung) sowie die komplette Extras-Liste (ersetzt die erkannten
  Extras). Auch korrekt erkannte Felder sind überschreibbar („Weitere Felder
  überschreiben").
  - Manuelle Werte **überleben „Neu einlesen" und erneuten Import** (werden nach
    jedem Parse wieder angewendet) und schlagen das Parser-Ergebnis; der KI-Fallback
    füllt nur weiterhin fehlende Felder.
  - Leeres Feld speichern = Zuordnung löschen, der Parser-Wert gilt wieder.
  - Abgeleitete Werte (Paketpreis, Preis pro Nacht, Extras-Summe …) und die
    Statistik werden nach jeder Zuordnung neu berechnet; manuell gesetzte Felder
    erscheinen als ✍️-Chip in der Debug-Ansicht.
  - Neu: `PATCH /api/trips/<id>/fields`; Preis-Eingaben werden normalisiert
    („2000,00" → „2.000,00"), Datumsfelder validiert (TT.MM.JJJJ).

## [0.46.8] - 2026-07-10

### Added
- **Meine Reisen: „🔁 Neu einlesen"-Button.** Liest das gespeicherte PDF einer Reise
  neu ein (z. B. nach einem Parser-Update wegen TUI-Layout-Änderung) — ohne Löschen
  und Neu-Upload. Gleiche Reise, PDF/Erstellungsdatum/Anhänge/Packliste bleiben
  erhalten; nur die ausgelesenen Daten werden aktualisiert
  (`POST /api/trips/<id>/rescan`).

## [0.46.7] - 2026-07-10

### Fixed
- **Meine Reisen: Handgepäck aus neuen TUI-PDFs nicht erkannt.** TUI hat die
  Beschriftung geändert: „Gr. Handgepäck 10kg (55x40x20cm) + Prio Boarding (HBAG)"
  statt „Großes Handgepäck 10 kg (HBAG)". Der Parser ankert jetzt auf dem über
  alle Formate stabilen Buchungscode `(HBAG)` — Beschriftung, Gewicht, Maßangabe
  und Zusatztext davor dürfen beliebig variieren.

## [0.46.6] - 2026-07-10

### Fixed
- **Buchungsscore scheiterte still bei abgeschnittener KI-Antwort.** Live beobachtet
  (Claude UND Gemini, je 200 OK, UI nur „fehlgeschlagen", nichts im Log): das
  Output-Budget von 1024 Tokens war mit Websuche zu knapp — Zwischentext des Modells
  zwischen den Suchaufrufen zählt mit, das Structured-Output-JSON wurde abgeschnitten
  und scheiterte still beim Parsen. Budget auf 2048 erhöht (Gemini bekommt die
  Thinking-Reserve weiterhin obendrauf).
- **Leere/abgeschnittene KI-Antworten sind jetzt diagnostizierbar:** WARNING-Logs für
  `stop_reason=max_tokens` (Anthropic), leere Antworten (beide Provider inkl.
  finish_reason) und ungültiges Buchungsscore-JSON (mit Text-Ausschnitt) — bisher
  waren diese Pfade komplett unsichtbar.

## [0.46.5] - 2026-07-10

### Changed
- **TripPilot Tagesausflug: Fragebogen gestrafft.** Die Frage „Was nervt dich im
  Urlaub?" entfällt im Tagesausflug-Modus (im Urlaubsmodus bleibt sie). Dafür gibt
  es am Ende ein neues optionales Freitext-Feld „Was macht für dich einen
  perfekten Ausflug aus?", das mit in den KI-Prompt einfließt.

## [0.46.4] - 2026-07-10

### Added
- **Buchungsscore berücksichtigt jetzt die Kalender-Trend-Historie.** Die größten
  Preisbewegungen aus dem Preiskalender (`calendar_history`, wie bei der
  KI-Kalenderanalyse, bis zu 8) gehen jetzt mit in die Buchungsscore-Fakten und
  den Prompt ein — inkl. Zusammenfassung „X von Y gestiegen". Steigen viele
  Reisetermine auf breiter Front, wertet die KI Warten als riskant (Signal für
  „jetzt buchen"); fallen viele, kann Warten sich lohnen. Gewichtung laut
  Instruktion ähnlich stark wie der eigene Preistrend.

## [0.46.3] - 2026-07-10

### Fixed
- **Tag-Leiste folgt jetzt der aktiven Ansicht.** Die Tag-Pills zeigten immer die
  Tags ALLER Angebote — mit aktivem Preisverlauf-Filter standen dort Tags von
  Angeboten, die gar nicht in der Liste waren (und umgekehrt). Jetzt erscheinen
  nur die Tags der aktuell sichtbaren Ansicht (Preisverlauf exklusiv; normale
  Ansicht inkl. Archiv nur, wenn eingeblendet). Aktive Tag-Filter, die es in der
  neuen Ansicht nicht gibt, werden automatisch abgewählt, statt die Liste
  kommentarlos zu leeren.

## [0.46.2] - 2026-07-10

### Changed
- **Preiskalender: „Größte Bewegungen seit letztem Abruf" einklappbar.** Die Liste
  ist jetzt standardmäßig eingeklappt (Kopfzeile zeigt die Anzahl der Bewegungen)
  und lässt sich per Klick auf-/zuklappen. Der Zustand bleibt beim Monatswechsel
  und Ansichts-Umschalten erhalten; beim Öffnen des Kalenders für ein Angebot
  startet sie wieder eingeklappt.

## [0.46.1] - 2026-07-10

### Fixed
- **Kalender-Preisänderung wurde bei Alt-Kalendern verschluckt.** Stammt der
  gespeicherte Kalender aus einer Version vor der Trend-Historie (< 0.43.11) — oder
  wurde die Historie geleert —, fehlte für geänderte Tage der Vorwert in
  `calendar_history`: `_calendar_moves()` fand kein Delta, der
  `calendar_trend_min_diff`-Filter sah 0 € und unterdrückte Benachrichtigung und
  Trend-Badge, obwohl sich der Preis real geändert hatte (z. B. Kalendertag
  1.999 € → 2.026 € ohne „📅 Kalenderpreise geändert“-Meldung).
  `_store_calendar_snapshot` trägt den Vorwert jetzt aus dem alten Cache-Snapshot
  rückdatiert nach (Baseline-Heilung) — Delta, Trend-Ansicht und Alarm
  funktionieren damit auch für Kalender aus der Zeit vor dem Feature.

## [0.46.0] - 2026-07-09

### Changed
- Preisverlauf-Angebote (`history_only`) laufen jetzt in einem festen, gestreuten
  Tages-Slot (09:00 lokal + individueller Offset je Angebot) statt "24h nach
  letztem Check" — kein Burst mehr, alle zur gleichen Zeit.
- Ort des Suchtreffers wird beim Tracken (normal, „Alle tracken", „3 tracken")
  automatisch als Tag gesetzt.
- Preisverlauf-Toggle auf der Startseite ist jetzt exklusiv (zeigt nur diese
  Angebote, statt sie an die normale Liste anzuhängen); Toggle-Leiste bereinigt.

### Added
- Bei fehlgeschlagenem Preis-Abruf zeigt die Karte jetzt den letzten bekannten
  Preis durchgestrichen statt nur einen Strich.
- Angebote werden nach 3 Fehlschlägen in Folge automatisch pausiert (statt nur
  benachrichtigt) — spart sinnlose Wiederholversuche auf tote URLs/dauerhaft
  ausgebuchte Hotels. Gilt auch für history_only, dort ohne Benachrichtigung.

### Fixed
- Tag-Chips fehlten in der schlanken Preisverlauf-Karte (Tag war gesetzt, nur
  unsichtbar) — TUI-Link fehlte dort ebenfalls und wurde ergänzt.

## [0.45.6] - 2026-07-09

### Added
- Preisverlauf-Tracking für reine Vergleichs-Hotels: in der Suche „📊 3 tracken"
  übernimmt günstigstes, mittleres und teuerstes Hotel der Treffer automatisch
  ins Tracking (`history_only`) — ohne Zimmerauswahl-Dialog, ohne Benachrichtigungen.
  Diese Angebote werden nur 1×/Tag geprüft (statt im normalen `poll_interval`),
  inklusive Preiskalender. Auf der Startseite standardmäßig ausgeblendet, per
  neuem Umschalter „📊 Preisverlauf" einblendbar; eigene, schlanke Karte zeigt
  nur Preis/Verlauf/Kalender. Preisbewegungen fließen normal in den Markttrend ein.

## [0.45.5] - 2026-07-09

### Fixed
- `init: true` (0.45.4) allein reichte nicht: Supervisor konnte SIGTERM jetzt
  zwar zustellen, Python hatte aber keinen eigenen Handler → Default-Handler
  killt den Prozess (exit 143), Supervisor beschwert sich zu Recht ("should
  trap SIGTERM ... exit with code 0"). Eigener `SIGTERM`-Handler ergänzt
  (`os._exit(0)` — alle Hintergrund-Threads sind daemon, kein Cleanup nötig).
  Live verifiziert: sauberer Exit-Code 0.

## [0.45.4] - 2026-07-09

### Fixed
- Add-on beendete sich bei jedem Update/Neustart mit Exit-Code 137 (SIGKILL statt
  sauberem Stop). Ursache: `Dockerfile` basiert auf reinem `debian:bookworm-slim`
  ohne eigenes Init-System, `run.sh` macht den Flask-Prozess per `exec` zu PID 1 —
  ohne eigenen Signal-Handler ignoriert der Kernel bei PID 1 unbehandelte Signale
  wie SIGTERM (Linux-Sonderfall), der Supervisor musste nach Timeout hart killen.
  `init: false` → `init: true` in `config.yaml`: HA Supervisor stellt jetzt ein
  Mini-Init als echte PID 1, das Signale korrekt durchreicht.

## [0.45.3] - 2026-07-09

### Changed
- HA-Sensoren melden bei fehlendem Preis/zu wenig Daten jetzt `unknown` statt
  `unavailable` (Angebots-Sensor, Übersicht, Markttrend) — `unavailable` ist in
  Home-Assistant-Konvention für einen kaputten/nicht erreichbaren Sensor
  reserviert, hier ist der Sensor ja da, nur (noch) kein Wert bekannt.

## [0.45.2] - 2026-07-08

### Fixed
- Hotelsuche mit Startdatum in der Vergangenheit (z. B. stehengebliebenes altes
  Datum im Suchformular) führte zu TUIs nichtssagendem HTTP 500 statt einer
  brauchbaren Fehlermeldung — wird jetzt vorher client- und serverseitig
  abgefangen (klare deutsche Meldung, kein unnötiger API-Call an TUI).

### Added
- „Heute"-Button neben dem Startdatum in der Suchmaske, springt aufs aktuelle
  Datum. Datumsfelder erlauben jetzt auch im Browser-Picker kein Datum in der
  Vergangenheit mehr (`min`-Attribut).

## [0.45.1] - 2026-07-08

### Fixed
- Code-Review-Nachbesserungen (Robustheit, keine funktionalen Nutzer-Änderungen):
  - 4 Stellen mit ungeschütztem `json.loads()` auf DB-Feldern (Vergleich-/Nächte-/
    Kalender-Cache, Angebots-Tags) crashen bei kaputten Daten nicht mehr, sondern
    fallen sauber zurück (neuer Helper `_json_loads_safe`).
  - `_ai_summary_cache`/`_booking_score_cache` jetzt mit Lock geschützt (bisher
    einzige In-Memory-Caches ohne Lock) — verhindert, dass zwei gleichzeitige
    Anfragen fürs gleiche Angebot je einen unnötigen bezahlten KI-Call auslösen.
  - Bisher stillschweigend verschluckte Fehler (`load_config()`, `hotel_from_url()`,
    `travellers_from_url()`, Start-Benachrichtigung) werden jetzt geloggt.
  - `POST /api/rooms/<id>` validiert den Zimmercode jetzt (kurzes alphanumerisches
    Format statt beliebiger String).

## [0.45.0] - 2026-07-08

### Added
- **KI-Verlauf: Anfrage wiederholen** — neuer 🔁-Button je Verlaufseintrag, fragt mit
  welcher KI (Claude oder Gemini) erneut angefragt werden soll und speichert das
  Ergebnis als neuen Verlaufseintrag (Original bleibt erhalten). Dafür wird ab jetzt
  der exakte Prompt-Text jeder KI-Analyse mitgespeichert (`ai_analyses.prompt`,
  neue Spalte) — ältere, vor diesem Update gespeicherte Einträge haben keinen Prompt
  und zeigen daher keinen 🔁-Button.

## [0.44.6] - 2026-07-08

### Changed
- Tracken eines Hotels aus der Suche startet die erste Preisprüfung nicht mehr
  sofort, sondern erst NACH der Zimmerauswahl (explizite Wahl oder Schließen des
  Dialogs = ursprüngliches Zimmer aus der Suche). Bisher wurde sofort mit dem
  ggf. falschen Zimmer aus dem Suchergebnis getrackt, noch bevor der Nutzer im
  Zimmerauswahl-Dialog wählen konnte. Betrifft nur den Einzeltrack-Button in der
  Suche — "Alle tracken" und das Tracken einzelner Kalendertage starten weiterhin
  sofort (kein Zimmerauswahl-Schritt dort).

## [0.44.5] - 2026-07-08

### Added
- Detail-Logging für Kalender-Preisänderungen bei aktiviertem `verbose_log`: loggt
  intern (nicht in der Benachrichtigung) exakt welche Reisedaten sich wie geändert
  haben, inkl. Warnung, falls ein als "geändert" gemeldetes Datum keine 2-Punkt-
  Historie mehr hat — zur Diagnose von Fällen, in denen die Meldung nicht mit dem
  im Kalender sichtbaren Preisverlauf übereinstimmt.

## [0.44.4] - 2026-07-08

### Added
- Neue Option `calendar_trend_min_diff` (Standard 20 €): Mindest-Preisänderung pro
  Reisedatum, ab der `notify_calendar_trend` benachrichtigt. Bisher löste jede noch
  so kleine Änderung (z. B. 10 € bei 2000+ € Reisepreis) sofort HA/Telegram aus —
  die Kalender-Trend-Ansicht selbst zeigt weiterhin jede Änderung, nur die
  Benachrichtigung wird jetzt gefiltert. 0 = Schwelle aus (altes Verhalten).

## [0.44.3] - 2026-07-08

### Fixed
- TripPilot Tagesausflug-Modus lieferte im KI-Prompt einen irrelevanten Hinweis
  zu „Pauschalreise (TUI)" und Flügen (Copy-Paste-Rest aus dem regulären
  Reiseberater-Block) — ein Tagesausflug hat weder Flug noch Pauschalreise.
  Klausel gilt jetzt nur noch für den regulären Reiseberater mit eigener
  Anreise (Auto/Bus/Bahn).

## [0.44.2] - 2026-07-07

### Added
- Retry-Button bei fehlgeschlagenen KI-Anfragen (Buchungsscore, Region-Ausblick,
  Kalender-Analyse, KI-Fazit, KI-Vergleich, Portfolio-Frage, TripPilot): transiente
  Fehler (z. B. 503 UNAVAILABLE bei hoher Last, egal ob Claude oder Gemini) zeigen
  jetzt „🔄 Erneut versuchen" statt nur eine tote Fehlermeldung. Bei
  Validierungsfehlern (z. B. „kein API-Key", „keine Daten") erscheint bewusst kein
  Retry-Button, da Wiederholen ohne Änderung nichts bringt.

## [0.44.1] - 2026-07-07

### Changed
- „Schwelle für Markttrend"-Option war ans Ende der HA-Add-on-Einstellungen sortiert
  (thematisch falsch platziert) — jetzt direkt neben `poll_interval` einsortiert.

### Added
- Neue Option `trippilot_home_location` (PLZ/Ort): belegt die TripPilot-Frage „Von wo
  geht's los?" (Auto/Bus/Bahn-Anreise, Tagesausflug) vor, damit man sie nicht bei jedem
  Durchlauf neu eintippen muss — im Fragebogen weiterhin änderbar.

## [0.44.0] - 2026-07-07

### Changed
- README aktualisiert: Preiskalender (Trend-Ansicht, Benachrichtigung, KI-Analyse),
  Markttrend und KI-Buchungsscore ergänzt (waren seit ihrer Einführung nicht in der
  README erwähnt).

## [0.43.15] - 2026-07-07

### Added
- **KI-Analyse im Preiskalender**: neuer Button „🤖 KI-Analyse" im Kalender-Modal —
  fasst die Kalenderpreise (Monatsdurchschnitte) und, falls vorhanden, aufgetretene
  Preisänderungen zusammen und empfiehlt günstige/teure Monate. Funktioniert
  gleichermaßen mit Claude und Gemini (reiner Markdown-Fließtext ohne Websuche, umgeht
  damit die bekannte Gemini-Einschränkung Structured-Output+Websuche von vornherein).
  6h gecacht wie die übrigen KI-Buttons.

## [0.43.14] - 2026-07-07

### Added
- **Benachrichtigung bei Kalender-Preisänderung**: ändert sich im Preiskalender eines
  Angebots ein Preis für ein bereits bekanntes Reisedatum, kommt jetzt eine
  Benachrichtigung über Home Assistant, Telegram **und** im wöchentlichen
  Wochenüberblick — bewusst grob (Hotelname + betroffener Monat/Monate, kein Datum,
  kein Preis; Details siehe Kalender-Grid). Neuer Schalter `notify_calendar_trend`
  (Standard an).

## [0.43.13] - 2026-07-07

### Added
- **„Kalender"-Button leuchtet bei Preisänderung**: hat sich seit dem letzten Öffnen
  des Preiskalenders ein Preis für ein Reisedatum geändert, pulsiert der Button
  (amber) bis der Kalender wieder geöffnet wurde — dann erlischt es bis zur nächsten
  echten Bewegung.

## [0.43.12] - 2026-07-07

### Added
- TripPilot: „FKK" als Aktivitäts-Option ergänzt

## [0.43.11] - 2026-07-07

### Added
- **Preiskalender: Trend über Zeit.** Der Preiskalender wurde bisher bei jedem Abruf
  komplett überschrieben — es war nicht sichtbar, ob Preise für ein bestimmtes
  Reisedatum steigen oder fallen. Jetzt wird die Historie delta-codiert mitgeschrieben
  (`calendar_history`, nur geänderte Tage) und ausgewertet:
  - **Trend-Ansicht** im Kalender-Grid (Umschalter „📈 Trend“/„💰 Preis“): Zellen zeigen
    die Preisänderung seit dem letzten Abruf statt/zusätzlich zum absoluten Preis
    (rot = gestiegen, grün = gefallen).
  - **Preisverlauf pro Tag**: Klick auf das 📈-Symbol in einer Zelle zeigt ein
    Mini-Diagramm mit dem Preisverlauf genau dieses Reisedatums über alle Abrufe.
  - **„Größte Bewegungen seit letztem Abruf“**-Liste im Kalender-Modal.
  - Die Historie wird beim Löschen/Zurücksetzen eines Angebots mitgelöscht und im
    Backup/Restore wie der Preisverlauf mitgesichert (`tuiwatch_backup` Version 4).

### Fixed
- `_check_cheaper_date()` rief bei **jedem** erfolgreichen Preis-Check den kompletten
  Preiskalender neu ab (bis zu 6 HTTP-Requests), ohne die 7-Tage-Cache-TTL zu beachten,
  die der Buchungsscore bereits nutzt. Nutzt jetzt dieselbe TTL — die „günstigerer
  Termin“-Prüfung bleibt bei jedem Check aktiv, nur der teure Abruf wird gedrosselt.

## [0.43.10] - 2026-07-07

### Fixed
- Abgelaufene Session im sekundären Healthcheck-Poll nicht erkannt: `loadHealth()` ignorierte 401-Antworten still, Status-Punkt blieb eingefroren statt zum Login weiterzuleiten (Hauptpoll `loadOffers()` hatte das bereits)

## [0.43.9] - 2026-07-06

### Added
- **Hotelsuche: Filter „Nur Erwachsene"** (Adults-Only-Hotels). TUI übersetzt
  `facilityAttributes=13` clientseitig in einen `logicalExpression`-Code, bevor die
  Anfrage an die Such-API geht — genau wie beim „Lage"-Filter kennt die API keine
  einfache ID. Der Code wurde nicht geraten, sondern per Playwright live abgefangen
  (echten Netzwerk-Request auf tui.com mitgeschnitten) und gegen die echte Such-API
  verifiziert (Gran Canaria: 100 → 28 Treffer, durchgehend adults-only-artige Hotels).

## [0.43.8] - 2026-07-06

### Fixed
- **Buchungsscore gewichtete Kalender-Saisonalität zu stark:** die Anweisung
  unterschied nicht klar zwischen „welcher Monat ist saisonal günstiger" (Kalender)
  und „ist JETZT ein guter Zeitpunkt zu buchen" (Preistrend/Markttrend) — bei langer
  Vorlaufzeit konnte das dazu führen, dass ein saisonal günstiger Reisemonat allein
  schon für ein "jetzt buchen" sprach, obwohl sich der Preis bis zum Abflug noch
  deutlich ändern kann. Anweisung ergänzt: bei langer Vorlaufzeit zählt die
  Saisonalität weniger, Preistrend/Markttrend mehr; zusätzlich die allgemeine
  Frühbucher-Erfahrung (eher früh buchen, da Preise Richtung Abflug oft steigen).

## [0.43.7] - 2026-07-06

### Added
- **Buchungsscore frischt Preiskalender bei Bedarf auf:** fehlt für ein Angebot noch
  ein Preiskalender oder ist er älter als 7 Tage, wird er jetzt einmalig automatisch
  abgerufen, bevor der Buchungsscore berechnet wird (macht nur diesen einen Aufruf
  spürbar langsamer). Ist er noch frisch, bleibt er unverändert — kein Abruf bei
  jedem Klick. Ohne Preis für das Angebot wird gar nicht erst versucht.

## [0.43.6] - 2026-07-06

### Fixed
- **Buchungsscore verschätzte sich bei der Vorlaufzeit:** der Prompt enthielt nirgends
  das heutige Datum, die KI musste "heute" selbst raten und hielt eine Reise im
  Mai 2027 fälschlich für "fast drei Jahre" entfernt statt gut ein Jahr. Heutiges Datum
  sowie geschätztes Abreisedatum + Tage/Monate bis Abreise werden jetzt selbst berechnet
  (nicht der KI überlassen) und explizit in den Prompt aufgenommen (pro Angebot und
  pro Destination).

## [0.43.5] - 2026-07-06

### Fixed
- **CodeQL-Alerts #185/#186 (SQL query built from user-controlled sources):**
  `_market_moves_query()` baute den SQL-Text abhängig von den übergebenen Filtern
  zusammen (String-Verkettung je nach gesetzten Bedingungen) — auch wenn nur Werte
  parametrisiert wurden, stuft CodeQL laufzeitabhängig zusammengebaute Query-Strings
  pauschal als riskant ein. Jetzt ein fester Query-Text mit `(? IS NULL OR spalte=?)`
  je Filter, keine Verkettung mehr abhängig von Eingaben.

## [0.43.4] - 2026-07-06

### Fixed
- **Angebots-Fußzeile:** „Zuletzt: ..."/Status-Text steht jetzt in einer eigenen Zeile
  über den Buttons statt sich mit ihnen eine Zeile zu teilen — Buttons waren dadurch
  bis zur Unlesbarkeit gekürzt. Button-Zeile hat jetzt die volle Breite für sich.
- **Zurücksetzen:** neben Löschen verschoben, ebenfalls als Icon (Kreispfeil) statt
  Textbutton.

## [0.43.3] - 2026-07-06

### Fixed
- **Angebots-Fußzeile umbrach:** gleicher Fix wie bei Werkzeugleiste/Kopfzeile —
  Buttons füllen die volle Breite und schrumpfen gemeinsam statt umzubrechen.
- **Löschen-Button:** von Textbutton auf rotes Papierkorb-Icon umgestellt (spart
  Platz in der ohnehin vollen Fußzeile).
- **Buchungsscore-Button:** Emoji entfernt.

## [0.43.2] - 2026-07-06

### Fixed
- **KI-Aufrufe mit Gemini konnten unabgefangen abstürzen:** nur `genai_errors.APIError`
  wurde gefangen — ein anderer SDK-interner Fehler (z. B. im
  Automatic-Function-Calling-Loop bei aktivierter Websuche) schlug bis zu Flask durch,
  das dann eine HTML-Fehlerseite statt JSON lieferte. Frontend zeigte dadurch nur die
  generische Meldung „KI-Zusammenfassung fehlgeschlagen" (live beobachtet: Google
  antwortete mit 200 OK, danach Absturz). Fängt jetzt jede Exception ab und liefert
  sauber `'failed'` zurück.

## [0.43.1] - 2026-07-06

### Fixed
- **Buchungsscore mit Gemini schlug fehl:** Gemini lehnt Websuche kombiniert mit
  strukturiertem JSON-Output kategorisch ab (400 INVALID_ARGUMENT — "Tool use with a
  response mime type ... is unsupported"). Bei beidem gleichzeitig gewinnt jetzt das
  Schema (nötig für den Buchungsscore), die Websuche entfällt für diesen Aufruf still.
  Betrifft nur Gemini als aktiven KI-Anbieter — Anthropic kombiniert beides.

## [0.43.0] - 2026-07-06

### Added
- **KI-Buchungsscore ("Orakel"):** neuer Button **🔮 Buchungsscore** je Angebot sowie
  **🔮** je Destination im Markttrend-Fenster. Auf Anfrage (kostet KI-Aufrufe inkl.
  Websuche, keine automatische Ausführung) schätzt die KI Score (0–100), Empfehlung
  (Jetzt buchen/Beobachten/Warten), Vertrauen sowie Erwartung für 7/30 Tage. Nutzt
  eigenen Preistrend, Markttrend/-index der Destination sowie — falls bereits
  abgerufen — die Saisonalität aus dem gespeicherten Preiskalender des Hotels
  (günstigster/teuerster Monat). Jeder Begründungspunkt ist als **[Daten]** oder
  **[Annahme]** gekennzeichnet, damit KI-Vermutungen nicht wie belastbare Fakten
  wirken. Ergebnisse werden 6h gecacht und landen im KI-Verlauf.

## [0.42.6] - 2026-07-06

### Fixed
- **Zimmerwechsel-Ausschluss versagte bei schnellem Ablauf:** Timestamps sind nur
  sekundengenau — wählte man direkt nach dem Tracken (Suche → sofort erscheinender
  Zimmerauswahl-Dialog) sofort ein Zimmer, landete das Room-Event oft in derselben
  Sekunde wie der erste Preis-Check. Der Vergleich `>` erkannte das nicht als „danach"
  und ließ den Zimmerwechsel-Preissprung fälschlich in den Markttrend einfließen. Jetzt
  `>=`. Bereits kontaminierte Daten lassen sich über **🔄 Neu berechnen** korrigieren.

## [0.42.5] - 2026-07-06

### Fixed
- **Kopfzeile umbricht/überlappt nie mehr:** gleicher Fix wie bei der Werkzeugleiste
  für die Buttons oben rechts (Alle prüfen/KI-Verlauf/Frage/Design). Zusätzlich
  behoben: die Grid-Spalte gab bei schmalem Fenster trotz `minmax(0,auto)` keinen
  Platz ab, weil `justify-self:end` das Element auf seine natürliche Breite setzt statt
  auf die Spaltenbreite — jetzt stretcht die Spalte, Ausrichtung passiert innen per
  `justify-content:flex-end`.

## [0.42.4] - 2026-07-06

### Fixed
- **Werkzeugleiste umbricht nie mehr:** Buttons verteilen sich jetzt per Flexbox
  (`flex:1 1 auto`) immer auf die volle Zeilenbreite (wie die Zeilen darüber/darunter)
  und schrumpfen bei schmalerem Fenster gemeinsam (Text wird bei Bedarf mit „…"
  gekürzt) statt in eine zweite Zeile umzubrechen.

## [0.42.3] - 2026-07-06

### Fixed
- **Werkzeugleiste umgebrochen:** der neue Markttrend-Button ließ die Buttons bei
  schmaleren Fenstern in eine hässliche zweite Zeile mit nur einem Button umbrechen.
  Toolbar-Buttons sind jetzt kompakter (weniger Padding/Schrift) — passt ab ~1000px
  Breite wieder in eine Zeile.

## [0.42.2] - 2026-07-06

### Added
- **Markttrend neu berechnen:** Button **🔄 Neu berechnen** im Markttrend-Fenster baut
  `price_moves` komplett aus der vorhandenen Preishistorie neu auf. Behebt z. B. einen
  Zimmerwechsel-Preissprung, der vor der Zimmerwechsel-Korrektur bereits fälschlich
  mitgezählt wurde — ohne die gesammelten Daten zu verlieren.

## [0.42.1] - 2026-07-06

### Fixed
- **Markttrend zeigte fälschlich „stabil":** die Richtung wurde aus dem einfachen
  Mittelwert aller Preis-Checks berechnet — die vielen „unverändert"-Checks zwischen
  zwei echten Preisschritten (Preise ändern sich seltener als der Poll-Intervall)
  verwässerten einen echten Anstieg/Rückgang fast auf null. Die Richtung basiert jetzt
  auf der kumulierten (Zinseszins-verketteten) Bewegung.
- **Zimmerwechsel verfälschte den Markttrend:** wählt man für ein Angebot ein anderes
  Zimmer, wurde der dadurch ausgelöste Preissprung bisher als Marktbewegung gezählt.
  Dieser eine Schritt wird jetzt ausgeklammert (Zählung setzt danach neu an).

### Added
- **Schwelle konfigurierbar:** neue Option `market_trend_threshold` (%, Standard 1.0)
  legt fest, ab welcher kumulierten Bewegung der Markttrend als steigend/fallend statt
  stabil gilt.
- **Index seit Aufzeichnungsbeginn:** zusätzlich zum rollierenden 14-Tage-Trend zeigt
  „Markttrend" je Destination einen Index (Basis 100) über die komplette Historie —
  fängt auch langsame, über Wochen verteilte Bewegungen ab, die aus dem 14-Tage-Fenster
  herausfallen würden.

## [0.42.0] - 2026-07-06

### Added
- **Globaler Markttrend:** neuer Button **📈 Markttrend** zeigt den marktweiten
  Preistrend über alle geprüften Angebote der letzten 14 Tage, aufgeschlüsselt nach
  Reisedestination. Anders als der bisherige Trend je Angebot (aus dessen eigener
  Historie) basiert dieser auf den Prozent-Änderungen aller Angebote zueinander (macht
  unterschiedlich teure Hotels vergleichbar) und liegt in einer eigenen Tabelle, die
  **unabhängig vom Fortbestehen einzelner Angebote** ist — das Löschen eines Angebots
  hat keinen Einfluss auf den Markttrend. Beim ersten Start nach diesem Update wird die
  vorhandene Preishistorie einmalig rückwirkend eingerechnet. Zusätzlich neuer
  HA-Sensor `sensor.tuiwatch_markttrend`.

## [0.41.10] - 2026-07-06

### Changed
- **Verlaufstabelle ohne Preis-Rauschen:** Zeilen ohne Preisänderung zum
  vorherigen Abruf werden jetzt ausgeblendet — außer dem jüngsten Eintrag
  (zeigt weiterhin, wann zuletzt geprüft wurde). Fehlgeschlagene Checks
  bleiben sichtbar.

## [0.41.9] - 2026-07-06

### Added
- **Preisänderung im Verlaufsdiagramm:** in der Zeitreihen-Tabelle im
  Verlaufs-Modal zeigt jede Zeile jetzt die Änderung zum vorherigen Preis als
  Badge (▲ rot bei Anstieg, ▼ grün bei Rückgang) — wie die bestehenden
  Delta-Badges auf den Angebotskarten.

## [0.41.8] - 2026-07-06

### Added
- **2 neue Binär-Sensoren:** `binary_sensor.tuiwatch_api_available` (an, solange
  alle kritischen TUI-Endpunkte beim letzten Selbsttest erreichbar waren) und
  `binary_sensor.tuiwatch_cooldown_active` (an, solange der globale „Jetzt
  prüfen"-Cooldown läuft). Wie der Coupon-Sensor werden beide per Timer laufend
  erneut gemeldet und sind daher direkt nach einem HA-Neustart wieder verfügbar.

## [0.41.7] - 2026-07-05

### Added
- **Cooldown auf scraping-lastigen Routen:** `/api/check-now` (60s global),
  `/api/search` (3s pro IP) und `/api/searches/<id>/check` (30s pro Suchabo)
  lehnen wiederholte Aufrufe innerhalb der Wartezeit jetzt mit 429 ab, statt
  bei mehrfachem Klicken/Skript-Aufrufen parallel gegen TUI zu scrapen —
  schützt davor, dass die eigene IP dort geblockt wird.

## [0.41.6] - 2026-07-05

### Added
- **Suchleiste im KI-Verlauf:** filtert die gespeicherten Fazits/Vergleiche
  live nach Titel, Art (Fazit/Vergleich/Frage/TripPilot) und Modell.

## [0.41.5] - 2026-07-05

### Fixed
- **Gemini: Auto-Tags ohne Fehler aber ohne Tags, Wochenüberblick-Text riss
  mitten im Satz ab:** Gemini teilt sich das `max_output_tokens`-Budget
  intern mit „Thinking"-Tokens (bei Anthropic nicht genutzt) — bei knapp
  bemessenen Werten (Auto-Tags 300, Wochenüberblick 500) verbrauchte das
  Thinking das komplette Budget, sodass die eigentliche Antwort leer oder
  abgeschnitten zurückkam, ohne dass ein Fehler auftrat. Betrifft nur
  Gemini als aktiven Anbieter. Fix: Reserve von 2048 Tokens für Thinking
  wird jetzt automatisch auf jede Gemini-Anfrage draufgeschlagen.

## [0.41.4] - 2026-07-05

### Changed
- **„❓ Frage" (Frag dein Portfolio) nutzt jetzt auch Websuche:** bisher
  wurde die KI angewiesen, ausschließlich anhand der Portfolio-Daten zu
  antworten — Fragen wie „wie ist das Wetter zur Reisezeit?" liefen ins
  Leere, obwohl Websuche technisch längst aktiv war. Portfolio-Fakten
  (Preis/Sterne/Trend/Tags) bleiben verbindliche Grundlage, für alles
  darüber hinaus recherchiert die KI jetzt aktiv statt nur auf fehlende
  Daten zu verweisen.

## [0.41.3] - 2026-07-05

### Added
- **Zielregion jetzt Mehrfachauswahl:** Balearen, Italien, Frankreich,
  Griechische Inseln, Adriaküste, Algarve, Zypern ergänzt (Klammer-Texte bei
  bestehenden Chips entfernt). Mehrere Regionen gleichzeitig wählbar (z. B.
  Balearen + Griechische Inseln), „Tagesausflug in der Nähe" bleibt dabei
  exklusiv — schließt automatisch alle anderen Regionen aus und umgekehrt.
  Neue generische „exklusive Option"-Logik in der Wizard-Engine, direkt auch
  für „Kein Gewässer nötig" (Meer/See-Frage) genutzt, das bisher fälschlich
  mit Meer/See kombinierbar war.

### Changed
- **Länder-Ausschluss nur noch bei „Weltweit"/„Egal" sichtbar** — bei einer
  konkreten Zielregion (z. B. Balearen) ergibt die Frage keinen Sinn und
  wird jetzt übersprungen.

## [0.41.2] - 2026-07-05

### Fixed
- **Kosten-Anzeige rundete auf $0.00:** bei kleinen Beträgen (z. B. Gemini
  Flash mit wenigen Tokens) wurden die Preise korrekt berechnet, aber mit
  nur 2 Nachkommastellen angezeigt und damit unsichtbar. Zeigt jetzt bei
  Beträgen unter $0.01 automatisch 4 Nachkommastellen.
- Veralteten Hinweis „Anthropic-Listenpreis" entfernt (gilt jetzt auch für
  Gemini-Preise).

## [0.41.1] - 2026-07-05

### Added
- **KI-Anbieter im Footer umschaltbar:** sind beide API-Keys (Anthropic +
  Gemini) hinterlegt, zeigt der Footer den aktiven Anbieter an — Klick
  wechselt sofort zum anderen, ohne die Add-on-Konfiguration zu öffnen. Ist
  nur ein Key gesetzt, läuft alles automatisch über diesen (kein
  Umschalter nötig, `ai_provider` wird dann ignoriert).

### Fixed
- **Auto-Tags mit Gemini kaputt:** `additionalProperties` im Tag-Schema
  wurde von der echten Gemini-API mit 400 „Unknown name
  additional_properties" abgelehnt (obwohl das lokale SDK es klaglos
  akzeptierte) — wird jetzt vor jedem Gemini-Aufruf mit
  Structured-Output rekursiv aus dem Schema entfernt.
- **`ai_enabled`** berücksichtigte bisher nur `anthropic_api_key` — war nur
  `gemini_api_key` gesetzt, blieben alle KI-Buttons unsichtbar.

## [0.41.0] - 2026-07-05

### Added
- **Google Gemini als zweiter KI-Anbieter:** neue Option `ai_provider`
  (`anthropic`/`gemini`) schaltet global für alle KI-Features (KI-Fazit,
  Vergleich, TripPilot/Tagesausflug, Auto-Tags, Portfolio-Frage) um.
  Eigener API-Key (`gemini_api_key`) und Modellwahl (`gemini_model`:
  gemini-3.1-pro/3.5-flash/2.5-flash). Websuche über Google-Search-
  Grounding statt Anthropics `web_search`-Tool — `ai_max_web_searches`
  gilt weiterhin nur bei Anthropic, Gemini kennt kein Suchlimit.

## [0.40.8] - 2026-07-05

### Added
- **Anzahl Websuchen in der Antwort sichtbar:** zeigt jetzt „🔍 N Websuchen"
  neben Tokens/Kosten unter jedem KI-Ergebnis (Anthropic liefert die Zahl
  direkt in der Nutzungsstatistik mit).

## [0.40.7] - 2026-07-05

### Added
- **Neue Option `ai_max_web_searches`** (Standard 12, 1-50): deckelt, wie oft
  Claude pro KI-Aufruf selbst das Web durchsuchen darf. War bisher
  unbegrenzt, was bei umfangreichen Anfragen (z. B. Reiseberater mit 3
  Zielen + Unterkünften) zu sehr hohen Input-Token-Zahlen/Kosten führen
  konnte. Niedriger spart Tokens/Kosten, höher liefert gründlichere
  Antworten.

## [0.40.6] - 2026-07-05

### Fixed
- **Tagesausflug prüfte sinnlos auf Reisewarnungen** (KI narrierte das sogar
  im Ergebnis) — Reisewarnungs-Check ist jetzt nur noch Teil des normalen
  Urlaubsmodus, nicht mehr beim Tagesausflug.

## [0.40.5] - 2026-07-05

### Changed
- **Tagesausflug schlanker:** „Was ist dir im Urlaub wichtig?" (deckt sich
  mit „Welche Aktivitäten interessieren dich?") und „Wie warm soll es
  sein?" (Zielwahl über allgemeine Temperaturvorliebe ergibt bei einem
  50-600-km-Radius keinen Sinn) werden jetzt übersprungen. Aktivitäten um
  Chip „Natur" ergänzt.

## [0.40.4] - 2026-07-05

### Added
- Tagesausflug: Entfernungs-Chip „bis 50 km" ergänzt.

### Changed
- **„Weiter" ohne Auswahl:** Startort (PLZ/Ort) ist jetzt Pflichtfeld, sobald
  der Schritt angezeigt wird (Auto/Bus/Bahn/Tagesausflug) — „Weiter" bleibt
  deaktiviert bis eine Eingabe da ist, sonst würde die KI eine
  Entfernungsvorgabe ohne Startpunkt bekommen. Unterkunftsart hat jetzt eine
  „egal"-Option (war als einziges Single-Select ohne Escape-Option).

## [0.40.3] - 2026-07-05

### Changed
- **Reiseberater heißt jetzt TripPilot:** neuer Name + Icon (🗺️) in Button,
  Modal, Ergebnis-Titel, KI-Verlauf, „⚙ KI-Prompts" und Doku. Rein
  kosmetisch — interne IDs/Funktionsnamen unverändert.

## [0.40.2] - 2026-07-05

### Changed
- **„Meer?"-Frage aufgeteilt:** neue Frage „Meer oder See?" (Mehrfachauswahl,
  auch beides möglich) vor der Wassertemperatur-Frage. „Kein Gewässer nötig"
  blendet die Temperaturfrage aus.

## [0.40.1] - 2026-07-05

### Fixed
- **Hotelgröße-Frage überflüssig bei anderer Unterkunftsart:** „Wie groß
  darf das Hotel sein?" erscheint jetzt nur noch, wenn bei der
  Unterkunftsart „Hotel" gewählt wurde.

## [0.40.0] - 2026-07-05

### Added
- **Tagesausflug-Modus im Reiseberater:** bei der ersten Frage „Tagesausflug
  in der Nähe" wählbar. Blendet Länder-Ausschluss, Reiseart, Mitreisende,
  Budget, Unterkunft, Flug/Anreiseart und die Freitext-Felder aus, fragt
  stattdessen Startort/max. Entfernung und verfügbare Zeit (Vormittag/
  Nachmittag/Ganzer Tag/inkl. Abend) ab. Eigener KI-Instruktionstext (3
  Tagesausflugsziele mit Aktivität, Anfahrt, groben Öffnungszeiten/Eintritt,
  Einkehr-Tipp, keine Übernachtungsempfehlung), editierbar über „⚙
  KI-Prompts" (4. Sektion). Keine Reise-DNA-Erfassung für Tagesausflüge.
- Aktivitäten-Chips um Zoo/Tierpark, Therme/Wellness-Tag, Sehenswürdigkeit/
  Schloss, Kletterpark, Escape Room, Minigolf, Flohmarkt/Markt ergänzt.

### Fixed
- **Übersicht im Reiseberater-Ergebnis:** zeigte die gewählte Anreiseart
  (Auto/Bus/Bahn/…) nicht an, jetzt ergänzt.

## [0.39.32] - 2026-07-05

### Added
- **Eigene Anreise im Reiseberater:** neue Frage „Wie möchtest du anreisen?"
  (Flugzeug/Auto/Bus/Bahn/Ist mir egal). Bei Auto/Bus/Bahn werden Flugzeit/
  Abflughafen übersprungen, stattdessen Startort (PLZ/Ort) und maximale
  Entfernung abgefragt. Die KI schlägt dann nur noch Ziele in Fahrdistanz
  vor — gilt auch für den Alternative-Vorschlag; der Überraschungs-Vorschlag
  bleibt dabei ebenfalls in Fahrdistanz statt einen anderen Kontinent
  vorzuschlagen.

## [0.39.31] - 2026-07-05

### Added
- **Berge-Details:** wie schon bei Strand — wählt man ⛰️ Berge bei den
  Interessen, fragt der Reiseberater jetzt nach (sanfte Wanderwege,
  anspruchsvolle Gipfeltouren, Skigebiet, Aussicht/Panorama,
  Alm-/Hüttenromantik, Seilbahn/Gondel, ruhig/wenig Tourismus).
- **Aktivitäten-Chips erweitert:** Reiten, Segeln, Angeln, Klettern, Yoga,
  Tennis, Kajak/SUP, Bootsausflüge.
- **JS-Engine-Test:** `tuiwatch/tests/test_wizard_engine.js` prüft die
  `showIf`-Logik der bedingten Wizard-Schritte ohne npm-Dependency, läuft
  jetzt auch in der CI (`test-tuiwatch.yml`).

### Fixed
- **Temperatur-Schritt:** Option „egal" fehlte, jetzt ergänzt.

## [0.39.30] - 2026-07-05

### Fixed
- **Auto-Tags kaputt:** Anthropic lehnte den Structured-Output-Schema mit
  `"Error code: 400 ... maxItems is not supported"` ab. `maxItems` aus dem
  Tags-Schema entfernt, Kappung auf max. 4 Tags jetzt serverseitig nach der
  Antwort.

## [0.39.29] - 2026-07-05

### Changed
- **Strand-Details präzisiert:** „Langer Sandstrand"/„Felsen/gut zum
  Schnorcheln" durch feinere Optionen ersetzt (Feinsandig, Kies/Felsen,
  Naturstrand unberührt, Weitläufig kilometerlang, Flach abfallend,
  Schattenplätze/Palmen, Gut zum Schnorcheln als eigene Option).

## [0.39.28] - 2026-07-05

### Added
- **Reiseberater: Strand-Details:** wählt man bei „Was ist dir im Urlaub
  wichtig?" 🌴 Strand aus, erscheint jetzt ein Folge-Schritt zur genaueren
  Strandart (langer Sandstrand, kleine ruhige Bucht, belebt mit Beach-Bars,
  Felsen/Schnorcheln, direkt am Hotel, Fußweg/Promenade OK) — fließt in
  Zielwahl, Unterkunftsvorschläge und Reise-DNA mit ein. Der Wizard
  unterstützt intern jetzt generisch bedingte Folge-Schritte (`showIf`).

## [0.39.27] - 2026-07-05

### Fixed
- **Reiseberater: Unterkünfte passten nicht zum Ziel:** die KI nannte z. B.
  bei „Teneriffa Süd" Hotels auf Fuerteventura/Gran Canaria. Prompt verlangt
  jetzt explizit, dass alle genannten Unterkünfte in genau dem Ziel/der
  Teilregion aus der Überschrift liegen müssen.

## [0.39.26] - 2026-07-05

### Changed
- **Reiseberater empfiehlt jetzt konkrete Unterkünfte:** je Hauptvorschlag
  Budget/Mittelklasse/Gehoben mit je 2-3 Nennungen, passend zur gewählten
  Unterkunftsart (echte Namen bei Hotel/Apartment/Villa, konkrete
  Wohngegenden bei Ferienwohnung/Airbnb/Camping/Hostel). Nur überwiegend gut
  bewertete Unterkünfte laut Websuche; Hinweis, dass Verfügbarkeit/
  Buchbarkeit (bei TUI auch im Katalog) selbst live zu prüfen ist.

## [0.39.25] - 2026-07-05

### Fixed
- **Abgelaufene Session wird jetzt erkannt:** Lief die Login-Session ab
  (z. B. über Nacht bei offenem Browser-Tab), blieb die Seite scheinbar
  normal sichtbar, aber jeder Klick schlug fehl und die Konsole zeigte nur
  ein schwarzes Fenster. Jetzt wird bei abgelaufener Session automatisch
  neu geladen und die Login-Seite angezeigt. (Betrifft nur den direkten
  Zugriff, nicht HA Ingress.)

## [0.39.24] - 2026-07-04

### Changed
- Footer-Tagline „— verfolgt TUI-Reisepreise" entfernt, steht jetzt nur
  noch „TUIWatch vX.X.X · Prüfintervall: …".

## [0.39.23] - 2026-07-04

### Changed
- **Reiseberater-Fragebogen verfeinert:** Meer-Schritt jetzt mit konkreten
  Temperaturstufen (28°C+, 24–27°C, 20–24°C, egal, kein Meer nötig) statt
  vagem „badewarm wichtig". Unterkunftsart um „Ferienwohnung"/„Airbnb"
  ergänzt. Hotelgröße um „mittelgroß" zwischen Boutique und riesiger
  Clubanlage ergänzt.
- Footer zeigt jetzt die Add-on-Version („TUIWatch v0.39.23 — …").

## [0.39.22] - 2026-07-04

### Added
- **KI-Kosten pro Tag & Monat**, zusätzlich zur Gesamtsumme — neue Anzeige
  im Footer („🔢 KI heute … · Monat … · gesamt …"), auch im KI-Ergebnis-
  Fenster ergänzt. Alle drei Zähler liegen dauerhaft in der Datenbank
  (Label „seit Add-on-Start" war irreführend — die Gesamtsumme hat schon
  vorher jeden Neustart überlebt).
- **KI-Verlauf, Reise-DNA, Kosten-Zähler und eigene KI-Prompts sind jetzt
  Teil von Backup/Restore.** Bisher gingen sie bei einer Wiederherstellung
  verloren. Restore ist wie gehabt nicht-destruktiv: Einstellungen/Zähler
  werden nur übernommen, wenn lokal noch nichts hinterlegt ist — laufende
  Zähler werden nie durch ältere Backup-Werte überschrieben.

## [0.39.21] - 2026-07-04

### Fixed
- **Du-Anrede fehlte noch bei Hotelvergleich, KI-Fazit, Frag dein Portfolio
  und Wochenüberblick** — nur der Reiseberater hatte die Anweisung, die
  anderen KI-Antworten fielen auf Claudes Standard („Sie") zurück. Jetzt
  überall explizit „Du" vorgegeben.
- Hotelvergleich/KI-Fazit gaben teils Rechercheerzählung aus („Ich werde
  jetzt recherchieren…", „Lassen Sie mich noch prüfen…") statt direkt der
  fertigen Antwort — jetzt explizit im Prompt unterbunden.

## [0.39.20] - 2026-07-04

### Docs
- README/DOCS weisen jetzt deutlich darauf hin, dass die Anthropic-API
  kostenpflichtig ist und bei jedem KI-Aufruf reale Kosten entstehen
  (eigener API-Key/eigenes Konto, keine Abbuchung durch TUIWatch selbst).

## [0.39.19] - 2026-07-04

### Docs
- README/DOCS auf aktuellen Stand: neuer Abschnitt „🧭 Reiseberater"
  (Fragebogen, Alternative/Überraschung, Sicherheitsklauseln, Wind/Klima-
  Recherche, Reise-DNA) und „Eigene KI-Prompts" (⚙-Menü im Footer für
  Reiseberater/Hotelvergleich/KI-Fazit) dokumentiert.

## [0.39.18] - 2026-07-04

### Changed
- **Wind-Vergleich im Hotelvergleich verschärft.** Wind ist jetzt ein
  eigener Kriterien-Punkt (statt im Klima-Satz versteckt): pro Hotel eine
  konkrete Zahl (km/h/Beaufort, Reisemonat, ortsgenau), keine allgemeinen
  Regionsangaben. Landet zusätzlich als eigene Zeile mit direktem
  Zahlenvergleich in der Abschluss-Tabelle statt nur als Fließtext.

## [0.39.17] - 2026-07-04

### Fixed
- **Mausrad in Modals (z. B. KI-Verlauf) scrollte die Hauptseite statt des
  Modal-Inhalts.** Modals hatten kein `overscroll-behavior: contain` —
  Scroll-Chaining zur dahinterliegenden Seite behoben, betrifft alle
  Modals.

## [0.39.16] - 2026-07-04

### Added
- Start-Telegram-Nachricht zeigt jetzt die Add-on-Version.

## [0.39.15] - 2026-07-04

### Added
- **KI-Fazit jetzt auch editierbar.** Dritter Abschnitt im „⚙ KI-Prompts"-
  Menü im Footer, gleiches Muster wie Reiseberater/Hotelvergleich
  (Checkbox „Eigenen Prompt verwenden", vorausgefüllter Standard, Cache
  berücksichtigt den aktiven Prompt).

### Changed
- Wind-Recherche jetzt auch beim Hotelvergleich und KI-Fazit: möglichst
  ortsgenau je Hotel/Küstenabschnitt statt nur fürs Land als Ganzes
  (gemeinsame Kriterienliste `_AI_SECTIONS`, wirkt auf beide Features).

## [0.39.14] - 2026-07-04

### Added
- **Eigene KI-Prompts.** Neuer „⚙ KI-Prompts"-Link im Footer: Standard-
  Instruktionstext für Reiseberater und Hotelvergleich einsehen und per
  Checkbox „Eigenen Prompt verwenden" durch eigenen Text ersetzen.
  Sicherheitskritische Klauseln (Länder-Ausschluss, Reisewarnungs-Check,
  TUI-Verfügbarkeit, Reise-DNA-Kontext) bleiben beim Reiseberater immer
  fix und sind nicht überschreibbar. Hotelvergleich-Cache berücksichtigt
  jetzt den aktiven Prompt (kein veraltetes Ergebnis nach Prompt-Änderung
  mehr aus dem 24h-Cache).
- KI-Verlauf zeigt beim Reiseberater jetzt auch den gewählten Monat.

### Changed
- Klima-Recherche im Reiseberater berücksichtigt jetzt auch Windverhältnisse
  und recherchiert möglichst auf Insel-/Teilregion-Ebene statt nur fürs
  ganze Land (z. B. Kapverden: Sal vs. Boa Vista unterscheiden sich stark
  beim Wind).

## [0.39.13] - 2026-07-04

### Added
- **Wildcard-Vorschlag im Reiseberater.** Zusätzlich zu den 3 Empfehlungen
  und der „Alternative" schlägt Claude jetzt einen Abschnitt „🎲
  Überraschung" vor — ein Ziel außerhalb der gewählten Zielregion (andere
  Weltgegend), an das man wahrscheinlich nicht von selbst gedacht hätte,
  aber weiterhin unter Beachtung aller Ausschlüsse (Länder, Reisewarnungen,
  TUI-Verfügbarkeit).

## [0.39.12] - 2026-07-04

### Added
- **Reise-DNA im Reiseberater.** Jede Anfrage berechnet zusätzlich ein
  Präferenzprofil (Strand, Kultur, Nachtleben, Aktiv, Entspannung,
  Kulinarik, Familie, Preisbewusst) direkt aus den Fragebogen-Antworten —
  ohne zusätzlichen KI-Call/Kosten. Wird als Tabelle ans Ergebnis
  angehängt, über mehrere Anfragen hinweg gespeichert (gleitender
  Mittelwert) und der KI beim nächsten Mal als Zusatzkontext mitgegeben.
- Reisedauer: „9–12 Tage" ergänzt. Budget: „2000–3000 €" ergänzt.

### Changed
- KI antwortet im Reiseberater jetzt per Du statt per Sie.

## [0.39.11] - 2026-07-04

### Fixed
- **Ursache gefunden: AdGuard blockte das Freitextfeld.** IDs/Klasse
  `adv-*` wurden von AdGuards generischen Werbeblock-Filtern erkannt
  (Präfix „adv" = advertisement) und das Feld unsichtbar gemacht — bei
  jedem anderen Werbeblocker/Browser reproduzierbar. Alle betroffenen
  IDs/Klasse auf `reiseb-*` umbenannt. Kastengröße wieder auf normales Maß
  (wie „Frag dein Portfolio") zurückgesetzt.

## [0.39.10] - 2026-07-04

### Fixed
- **Freitextfelder im Reiseberater: zweiter Anlauf.** Kasten war weiterhin
  in einem frischen Edge-Profil ohne jede Vorgeschichte unsichtbar — reiner
  Cache-/Service-Worker-Fall damit ausgeschlossen. Textarea nutzt jetzt eine
  echte CSS-Klasse (`.adv-text`, im `<style>`-Block) statt Inline-`style`-
  Attribut, deutlich größer (min. 160px, 3px blauer Rahmen) und mit fest
  codierten Farben statt CSS-Variablen — maximal robust gegenüber allem,
  was Inline-Styles oder Variablen-Auflösung stören könnte.

## [0.39.9] - 2026-07-04

### Fixed
- **Freitext-Felder im Reiseberater kaum sichtbar.** Die beiden Textarea-
  Schritte (Länder-Ausschluss-Freitext, perfekter Urlaub, frühere Reisen)
  waren bei manchen Nutzern praktisch unsichtbar. Kasten jetzt mit
  Mindesthöhe (90px), deutlichem 2px-Akzentrahmen und hellerem Hintergrund
  plus Fallback-Farbwerten (falls CSS-Variablen aus irgendeinem Grund nicht
  greifen).

## [0.39.8] - 2026-07-04

### Changed
- **Reiseart im Reiseberater: Mehrfachauswahl.** „Pauschalreise (TUI)" und
  „Badeurlaub" (o. ä.) lassen sich jetzt kombinieren statt nur eine Option
  wählbar zu haben.

## [0.39.7] - 2026-07-04

### Added
- **Länder ausschließen im Reiseberater.** Neuer Schritt: Klick-Liste
  gängiger Ausschluss-Kandidaten (Türkei, Ägypten, Tunesien, Marokko,
  Kenia, Thailand, Sri Lanka, Dominikanische Republik, Mexiko, Malediven)
  plus Freitext für weitere Länder. Unabhängig davon prüft die KI für
  jedes in Betracht gezogene Land per Websuche aktuelle Reisewarnungen/
  Sicherheitshinweise des Auswärtigen Amts und schlägt betroffene Länder
  standardmäßig nicht vor, außer sie wurden ausdrücklich als Zielregion
  gewünscht.

## [0.39.6] - 2026-07-04

### Added
- **Reiseberater erweitert.** 9 weitere Fragebogen-Schritte: Aktivitäten
  (Tauchen, Wandern, Skifahren, Golf, Safari, Kulinarik …), Unterkunftsart
  & Hotelgröße, ausführliche Hotelwünsche (Erwachsenenhotel, Swim-Up,
  Privatpool, Hausriff, Homeoffice …), Flugzeit & Abflughafen, was im
  Urlaub nervt, sowie zwei Freitext-Schritte („perfekter Urlaub" und
  frühere Urlaubserfahrungen — Claude erkennt darin Hotelketten/-typen
  und leitet ähnliche Ziele ab). Neue Reiseart „Pauschalreise (TUI)"
  schränkt die Empfehlung auf Ziele ein, die TUI tatsächlich im Programm
  hat (per Websuche geprüft). Zielregion „Makaronesien" ergänzt (Kanaren/
  Madeira/Azoren/Kapverden), da Kapverden geografisch nicht zu Europa
  zählt. Jede Antwort endet zusätzlich mit einem „🔀 Alternative"-Vorschlag
  abseits des exakten Profils.

## [0.39.5] - 2026-07-04

### Changed
- **Toolbar entschlackt.** Backup/Restore sind keine Buttons mehr in der
  Toolbar, sondern schlanke Textlinks im Footer (wie „API-Status").
- **Header-Layout korrigiert.** Kopfzeile brach bei mehreren KI-Buttons
  in zwei Zeilen um, weil Logo- und Aktionen-Spalte gleich breit erzwungen
  waren; Spalten sind jetzt inhaltsbreit, Reisen-Countdown zentriert sich
  im verbleibenden Raum statt starr auf der gesamten Kopfzeilen-Mitte.

## [0.39.4] - 2026-07-04

### Added
- **KI-Reiseberater.** Neuer „🧭 Reiseberater"-Button in der Toolbar: geführter
  Fragebogen (Zielregion, Interessen, Reiseart, Mitreisende, Budget, Dauer,
  Reisezeit, Wetterwünsche) mit Klick-Auswahl statt Freitext. Claude schlägt
  danach 3 passende, real existierende Reiseziele vor — freie Empfehlung aus
  KI-Wissen plus Websuche für aktuelle Klimadaten, unabhängig vom eigenen
  Angebots-Portfolio. Landet wie Fazit/Vergleich/Frage im KI-Verlauf und ist
  per E-Mail versendbar.

## [0.39.3] - 2026-07-04

### Added
- **PDF-Parser-Fallback per KI.** Erkennt der Regex-Parser bei einer TUI-
  Reisebestätigung Felder nicht (z. B. nach einer TUI-Layout-Änderung),
  ergänzt Claude sie aus dem PDF-Text — ausschließlich die vom Regex-Parser
  als fehlend markierten Felder, bereits erkannte Werte bleiben unangetastet.
  Structured Output, keine Websuche. Ohne hinterlegten API-Key unverändertes
  Verhalten (reiner Regex-Parser wie bisher).

## [0.39.2] - 2026-07-04

### Added
- **Frag dein Portfolio.** Neuer „❓ Frage"-Button oben: Freitext-Frage zu
  allen aktiven getrackten Angeboten (z. B. „Welches Hotel ist gerade das
  beste Schnäppchen?") — Claude antwortet anhand von Preis, Ort, Sterne/
  Weiterempfehlung, Trend, Wunschpreis und Tags. Landet wie Fazit/Vergleich
  im KI-Verlauf und ist per E-Mail versendbar.

## [0.39.1] - 2026-07-04

### Added
- **Auto-Tag.** Neuer „🤖 Auto-Tag"-Button in der Sammelaktionsleiste der
  Angebotsübersicht: vergibt automatisch 2-4 passende Schlagworte aus einer
  festen Liste (Familie, Strand, Party & Nachtleben, Ruhe & Erholung,
  Wellness & Spa, Sport & Aktiv, Luxus, Budget, Alleinreisende, Kultur &
  Sightseeing, Adults Only, Golf) — ergänzt bestehende Tags, überschreibt
  sie nicht. Structured Output, keine Websuche nötig (schnell & günstig).

## [0.39.0] - 2026-07-04

### Added
- **Wochenüberblick als Fließtext.** Mit hinterlegtem `anthropic_api_key`
  fasst Claude den wöchentlichen Digest zusätzlich in 2-4 Sätzen zusammen
  (größte Ersparnis, dringendste Gelegenheit) — steht oben in Telegram-
  Nachricht und E-Mail, vor der gewohnten Listenform. Best effort: schlägt
  die Zusammenfassung fehl, wird der Digest trotzdem ganz normal verschickt.
- **KI-Analyse per E-Mail.** Neuer „✉ E-Mail senden"-Button im KI-Fazit/
  -Vergleich (auch aus dem KI-Verlauf) — sendet die Analyse als HTML-Mail,
  inkl. Empfänger-Autocomplete aus dem Nextcloud-Adressbuch (falls
  eingebunden), genau wie beim bestehenden Angebots-Mailversand.

## [0.38.9] - 2026-07-04

### Changed
- README/DOCS auf aktuellen Stand gebracht: KI-Fazit, -Vergleich, -Verlauf,
  Token-/Kosten-Anzeige, DB-Größe im Footer dokumentiert.

## [0.38.8] - 2026-07-04

### Added
- Geschätzte Kosten (≈ $X.XX) jetzt auch pro einzelner Analyse sichtbar,
  nicht nur als Gesamtsumme — landet damit auch im KI-Verlauf (ältere,
  vor diesem Update gespeicherte Einträge zeigen sie mangels
  gespeichertem Wert nicht nachträglich an).

## [0.38.7] - 2026-07-04

### Added
- Footer zeigt jetzt die Größe der SQLite-Datenbank an (z. B. „DB: 2.3 MB"),
  aktualisiert alle 5 Minuten.

## [0.38.6] - 2026-07-04

### Added
- **KI-Verlauf.** Neuer „🤖 KI-Verlauf"-Button oben neben „Alle prüfen":
  zeigt alle bisherigen KI-Fazits/-Vergleiche (dauerhaft in der Datenbank
  gespeichert, unabhängig vom 24h-Cache, bis zu 300 Einträge), anklickbar
  zum erneuten Anzeigen, einzeln löschbar.

### Changed
- Alle KI-Buttons (Fazit, Vergleich in Suche & Angebotsübersicht,
  KI-Verlauf) sind nur noch sichtbar, wenn ein Anthropic API-Key in den
  Add-on-Einstellungen hinterlegt ist.

## [0.38.5] - 2026-07-04

### Added
- KI-Fazit/-Vergleich berücksichtigt jetzt Klima zur Reisezeit: historische
  Wassertemperatur, Wetter/Sonnenstunden und Windverhältnisse für Ort und
  Reisemonat (Klimatabellen statt Tagesvorhersage — für weit in der Zukunft
  liegende Termine ist keine echte Vorhersage möglich, nur der langjährige
  Durchschnitt). Reisezeitraum (Startdatum) wird dafür aus der Suche mit
  übergeben.

## [0.38.4] - 2026-07-04

### Added
- **KI-Vergleich auch in der Angebotsübersicht.** Die bestehende
  Mehrfachauswahl (Checkbox → Sammelaktionsleiste „Prüfen/E-Mail/
  Archivieren/Löschen") hat jetzt zusätzlich „🤖 Vergleichen" — vergleicht
  bis zu 5 markierte, bereits getrackte Angebote mit derselben KI-Logik
  wie in der Suche (nutzt zusätzlich den gespeicherten Reise-Detailtext
  des Angebots als Kontext).

## [0.38.3] - 2026-07-04

### Added
- Kumulierte KI-Nutzung seit Add-on-Start: jedes Fazit/Vergleich zeigt jetzt
  zusätzlich Gesamt-Aufrufe, Gesamt-Tokens und grob geschätzte Kosten in USD
  (Anthropic-Listenpreis je Modell) — kein echtes Guthaben (das zeigt nur
  die Anthropic-Console), aber ein Anhaltspunkt ohne zusätzlichen Admin-Key.

## [0.38.2] - 2026-07-04

### Added
- KI-Fazit/-Vergleich zeigt jetzt den Token-Verbrauch der Analyse an
  (Input-/Output-Tokens, ggf. aus Prompt-Cache bediente Tokens; auch bei
  gecachten Ergebnissen aus dem letzten Aufruf sichtbar).
- „📄 PDF exportieren" im KI-Fazit/-Vergleich: öffnet eine druckoptimierte
  Ansicht in neuem Tab, aus der sich der Browser-Druckdialog direkt als PDF
  speichern lässt (kein Server-seitiges PDF-Rendering nötig).

## [0.38.1] - 2026-07-04

### Added
- **KI-Hotelvergleich.** Checkbox je Suchergebnis zum Auswählen (max. 5);
  schwebende Leiste mit „🤖 Vergleichen" ruft Claude einmal für alle
  gewählten Hotels auf — Antwort inkl. Vergleichstabelle und Empfehlung,
  welches Hotel für wen (Familie, Paar, Ruhe, …) am besten passt. Gilt für
  Regionen-Suche und Suche aus einem Angebot gleichermaßen (gleicher Code).

### Fixed
- KI-Fazit/-Vergleich schlug mit Claude Haiku fehl (`does not support
  programmatic tool calling`) — `web_search`-Tool braucht dafür explizit
  `allowed_callers: ["direct"]`.

## [0.38.0] - 2026-07-04

### Added
- **KI-Hotel-Fazit in der Suche.** Neuer „🤖 KI-Fazit"-Button je Suchergebnis:
  Claude (mit Web-Suche) durchsucht aktuelle Bewertungen (HolidayCheck,
  Tripadvisor, Google) und liefert eine ausführliche Einschätzung zu Lage &
  Strand, Zimmern, Restaurants & Bars, Pool/Wellness, Ausstattung und
  Preis-Leistung. Ergebnis wird pro Hotel zwischengespeichert (24 Std.), damit
  erneutes Öffnen keine neue Anfrage auslöst.
- Neue Add-on-Optionen `anthropic_api_key` (Passwortfeld) und `anthropic_model`
  (Auswahl Opus/Sonnet/Haiku/Fable) — ohne hinterlegten Key bleibt die Funktion
  inaktiv und zeigt einen entsprechenden Hinweis.

## [0.37.5] - 2026-07-04

### Fixed
- Coupon-Sensor wird jetzt alle 2 Minuten erneut aus dem Cache an HA gemeldet
  (Timer statt nur einmalig beim Add-on-Start) — bleibt so auch nach einem
  reinen HA-Neustart verfügbar, ohne dass ein manueller "Suchen"-Klick nötig ist.

## [0.37.4] - 2026-07-04

### Fixed
- Teilen-Banner zeigt „Schön war's!" statt „Gute Reise!", wenn die Reise
  bereits beendet ist (Enddatum in der Vergangenheit).
- Coupon-Sensor (`binary_sensor.tuiwatch_aktionscodes`) wird beim Start sofort
  aus dem letzten gespeicherten Abruf gemeldet, statt erst nach dem nächsten
  Live-Abruf (bisher nach HA-Neustart bis zum manuellen „Suchen"-Klick weg).

### Added
- Angebots-E-Mail (manueller Versand) listet jetzt auch Hin-/Rückflugzeiten,
  falls vorhanden.

## [0.37.3] - 2026-07-03

### Added
- **Reise teilen.** Neuer „📤 Teilen"-Button in der Reisen-Detailansicht: legt
  Countdown („X Tage Y Std" bzw. „Gute Reise!" bei bereits abgeflogenen Reisen),
  Reiseziel und Hotel über ein Strand-Banner und teilt das Bild per Web Share
  API (Fallback: Download), wenn der Browser Datei-Teilen nicht unterstützt.
  Schriftgröße schrumpft automatisch bei langen Zielen/Hotelnamen.

## [0.37.2] - 2026-07-03

### Added
- Packliste-Kopfzeile zeigt jetzt zusätzlich erledigt/offen an
  (`66/70 · 24 erledigt · 42 offen`), nicht nur die Gesamtzahl.

## [0.37.1] - 2026-07-03

### Added
- **Bevorstehende Reisen im Wochen-Digest.** Die E-Mail/Telegram-Zusammenfassung
  zeigt jetzt einen Abschnitt „🧳 Bevorstehende Reisen" mit allen künftigen
  (noch nicht abgeflogenen) gebuchten Reisen inkl. Zeitraum und Countdown in
  Tagen — bisher zeigte nur der Seiten-Header die jeweils nächste Reise an.

## [0.37.0] - 2026-07-03

### Added
- **Packliste pro Reise.** Neuer Abschnitt in der Reisen-Detailansicht: beim
  ersten Öffnen wird eine Vorlage (7 Kategorien, an ein mitgebrachtes
  Strandurlaub-Packlisten-PDF angelehnt) automatisch eingespielt — Items lassen
  sich danach frei abhaken, umbenennen, umkategorisieren, löschen und ergänzen
  (begrenzt auf 70 Einträge, damit der Ausdruck auf eine A4-Seite passt). Ein
  „🖨️ Drucken"-Button öffnet eine druckoptimierte Ansicht mit TUIWatch-Kopfbereich
  und Reisedaten (Ziel/Hotel/Zeitraum), „↺ Zurücksetzen" spielt die Vorlage neu ein.
  Auch in Backup/Restore (ZIP) mitgesichert.

## [0.36.2] - 2026-07-03

### Fixed
- CodeQL Path-Injection-Alerts (#179, #181, #182, #183) bei Reise-PDF-Pfaden
  behoben: `_trip_pdf_path` nutzt jetzt `werkzeug.safe_join` statt manueller
  `resolve()`/`relative_to()`-Prüfung — CodeQL erkennt `safe_join` als
  Sanitizer, die manuelle Variante nicht.

## [0.36.1] - 2026-07-03

### Fixed
- Dockerfile kopierte `nextcloud.py` nicht ins Image → `ModuleNotFoundError` beim
  Start. Ergänzt.
- DE/EN-Übersetzungen für die drei neuen `nc_*`-Add-on-Optionen ergänzt (in
  `translations/de.yaml`/`en.yaml` vergessen).

## [0.36.0] - 2026-07-03

### Added
- **Nextcloud-Adressbuch beim E-Mail-Versand.** Der Empfänger-Dialog („Als E-Mail
  senden" / Sammelaktion „E-Mail") bietet jetzt optional ein Autocomplete aus einem
  Nextcloud-Adressbuch (CardDAV) — neue Optionen `nc_addressbook_url` (volle
  Adressbuch-URL aus der Nextcloud-Kontakte-App), `nc_user`, `nc_app_password`.
  Ersetzt den bisherigen reinen `prompt()`-Dialog durch ein Eingabefeld mit
  Autocomplete; Freitext-Adressen bleiben weiterhin möglich, ohne Konfiguration
  ändert sich nichts.

## [0.35.0] - 2026-07-03

### Added
- **Lage-Badges in der Hotelsuche.** Treffer zeigen jetzt Pillen für zutreffende
  Lage-Attribute (Direkt am Strand, Strand < 500m, Sandstrand, Ruhig, Außerhalb) —
  live aus dem hotelseitigen `globalTypes`-Katalog des Suchresponse abgeleitet und
  gegen echte Filterergebnisse verifiziert. „Meerseite" fehlt bewusst: der Code taucht
  im Suchresponse nirgends auf, nur serverseitig fürs Filtern nutzbar.

## [0.34.0] - 2026-07-03

### Added
- **Aktionscode-Hinweis in der Hotelsuche.** Die TUI-Such-API liefert je Hotel im
  `globalTypes`-Katalog den Code `GT03-COUP`, sobald tui.com für dieses Hotel gerade
  einen Aktionscode/Coupon anzeigt (live gegen mehrere Regionen verifiziert — exakter
  Codevergleich, kein Fuzzy-Match). Suchergebnisse mit diesem Flag zeigen jetzt „%
  Aktionscode möglich" unter den Angebotsdetails.

## [0.33.2] - 2026-07-03

### Changed
- Tag-Filter unter der Suchleiste erlaubt jetzt Mehrfachauswahl (ODER-Verknüpfung:
  zeigt Angebote mit mindestens einem der ausgewählten Tags) statt nur einem Tag

## [0.33.1] - 2026-07-03

### Changed
- Anhänge-Pille („＋ PDF") in der Reise-Detailansicht steht jetzt direkt unter der
  Buttonzeile (PDF öffnen/Debug/schließen), nicht mehr ganz unten nach allen
  Reisedetails — vorher leicht zu übersehen

## [0.33.0] - 2026-07-03

### Added
- **Weitere PDFs bei „Meine Reisen".** In der Detailansicht lässt sich jetzt zusätzlich
  zur Reisebestätigung ein weiteres PDF hinterlegen (z. B. der Reiseplan) — reine
  Ablage, ohne Auswertung/Parsing. Anhänge erscheinen als Pille (📎 Dateiname, öffnen/
  entfernen per Klick) unter den Reisedetails. Werden beim Löschen der Reise mit
  entfernt und im Backup/Restore mitgesichert.

## [0.32.1] - 2026-07-03

### Changed
- Tags auf der Angebotskarte: stehen jetzt in der Titelzeile neben dem Hotelnamen
  (mit Abstand) statt in einer eigenen Zeile darunter — spart Platz

## [0.32.0] - 2026-07-03

### Added
- **Tags für Angebote.** Frei vergebbare Schlagworte je Angebot (z. B. „Strand",
  „Familie") — hinzufügen über die ＋-Pille auf der Karte, entfernen per Klick auf den
  Tag. Unter der Suchleiste erscheint eine Pill-Zeile mit allen aktuell verwendeten
  Tags; Klick filtert die Liste live (wie die Textsuche, kein Neuladen), erneuter Klick
  hebt den Filter wieder auf. Tags werden im Backup/Restore mitgesichert.

## [0.31.0] - 2026-07-03

### Added
- Offline-Banner (wie SysWatch): erkennt Verbindungsabbruch über `online`/`offline`-Events,
  `navigator.onLine`-Check beim Start und fehlgeschlagene `/api/offers`-Abrufe (3 Fehlversuche
  in Folge) — abdunkelndes Overlay mit „Neu laden"-Button, verschwindet automatisch sobald
  wieder Daten ankommen

## [0.30.1] - 2026-07-03

### Changed
- Verbose-Log der Such-API (`Such-API POST ...`) zeigt jetzt alle relevanten Suchparameter
  (Zeitraum, Dauer, Reisende, Verpflegung, Lage, Flughäfen, Airlines, Operator, Direktflug)
  statt nur der Regionen-ID — erleichtert Diagnose bei Suchproblemen

## [0.30.0] - 2026-07-03

### Added
- **Lage-Filter in der Hotelsuche.** Neue Checkbox-Zeile unter „Verpflegung": Direkt
  am Strand, Sandstrand, Strand < 500m, Meerseite, Ruhig, Außerhalb — Mehrfachauswahl,
  schränkt die Trefferliste weiter ein (funktioniert in allen Suchmodi: Regionen-Suche,
  Suche aus Angebot, eingefügte TUI-URL). Wird auch in gespeicherten Suchen/Suchabos
  mitgespeichert. Intern übersetzt TUIWatch die IDs in den `logicalExpression`-Code,
  den die TUI-Such-API erwartet (per Live-Test ermittelt und verifiziert — anders als
  bei der Verpflegung reicht die einfache ID hier nicht aus).

## [0.29.0] - 2026-07-03

### Added
- **HA-Binärsensor für Aktionscodes.** Neuer `binary_sensor.tuiwatch_aktionscodes`:
  **an**, solange aktuell öffentliche TUI-Aktionscodes verfügbar sind, sonst **aus**.
  Die einzelnen Codes (Wert, Code, Art) stehen als Attribut `coupons` zur Verfügung —
  damit lassen sich Automationen in Home Assistant bauen, ohne die TUIWatch-UI zu
  öffnen. Nutzt dieselbe `ha_sensors`-Option wie die bestehenden Preis-Sensoren.

## [0.28.1] - 2026-07-03

### Fixed
- **„Exakt"-Checkbox in der Hotelsuche (endgültig behoben).** Der Fix aus 0.27.2
  reichte `duration=exact` als String statt als `["exact"]`-Array durch — ein Live-
  Test gegen die echte TUI-Such-API zeigte aber, dass **beide** Varianten
  stillschweigend ignoriert werden und die API auf 7 Nächte zurückfällt. Die
  Such-API kennt „exact" gar nicht (anders als die Angebots-Detailseite). Berechnet
  jetzt stattdessen die Nächtezahl selbst aus dem gewählten Zeitraum (von/bis) und
  sendet sie als normale Zahl — verifiziert per Live-Abfrage: 13.08.–16.08. liefert
  jetzt korrekt 3-Nächte-Treffer statt 7. Betraf auch die eingefügte TUI-Such-URL
  (`duration=exact` wurde dort zuvor sogar komplett verworfen).

## [0.28.0] - 2026-07-03

### Added
- **Reise-Countdown im Header.** Ist unter „Meine Reisen" eine bevorstehende Reise
  gespeichert, zeigt der Header mittig einen Countdown bis zum Abflug (z. B.
  „Sal / Amilcar Cabral · noch 12 Tage 4 Std"). Die Abflugzeit stammt aus dem
  geparsten Hinflug der importierten PDF; ist kein Hinflug erkannt, wird 00:00 des
  Reisebeginns angenommen. Klick auf den Countdown öffnet „Meine Reisen". Ohne
  bevorstehende Reise bleibt das Widget ausgeblendet.

## [0.27.2] - 2026-07-03

### Fixed
- **„Exakt"-Checkbox in der Hotelsuche.** Bei aktivierter Checkbox wurde die
  Reisedauer entgegen der Auswahl trotzdem als 7 Nächte gesucht, statt der
  tatsächlichen Nächte zwischen von/bis (z. B. 3 Nächte bei 13.08.–16.08.). Ursache:
  der native TUI-Wert `duration=exact` wurde beim Aufbau des Such-API-Requests
  fälschlich in ein Array (`["exact"]`) verpackt statt als reiner String
  durchgereicht — die TUI-API ignorierte den Wert dadurch und fiel auf ihren
  Standard zurück.

## [0.27.1] - 2026-07-02

### Changed
- **Toolbar passt in eine Reihe.** Buttons „🔍 Hotels suchen" → **„Suche"** und
  „⬆ Wiederherstellen" → **„Restore"** umbenannt; dadurch passen alle Toolbar-Buttons
  auch auf schmaleren Fenstern in eine Zeile.

## [0.27.0] - 2026-07-02

### Added
- **🔔 Suchabo / Sammel-Alarm** (Backlog #7). Jede **gespeicherte Suche** lässt sich
  jetzt **beobachten**: Schwellenpreis (pro Person) setzen und TUIWatch führt die Suche
  regelmäßig aus (im `poll_interval`-Takt, mindestens stündlich). Gemeldet wird per
  **Telegram/HA**, wenn ein Hotel **neu unter die Schwelle** fällt oder ein gemeldetes
  **weiter fällt** — je Hotel wird der tiefste gemeldete Preis gemerkt (kein Spam);
  steigt es über die Schwelle und fällt später erneut, wird wieder gemeldet.
  Im UI: Abo-Zeile unter den gespeicherten Suchen (Beobachten, Schwelle, „Jetzt
  prüfen"), aktive Abos mit 🔔 im Dropdown, aktuelle Treffer als normale
  Trefferliste anzeigbar (inkl. „Tracken"). Neue Endpunkte:
  `PATCH /api/searches/<id>` und `POST /api/searches/<id>/check`.

## [0.26.8] - 2026-07-02

### Added
- **PDF-Import: 🔍 Debug-Modus** (Backlog #10). In der Reise-Detailansicht zeigt „Debug"
  den **bereinigten PDF-Text**, je Feld **erkannt/leer** (Chips) und das geparste JSON —
  so lässt sich bei einer künftigen TUI-Layout-Änderung ohne Code-Runde sehen, *warum*
  ein Feld nicht erkannt wurde. Schlägt ein Import komplett fehl (422), öffnet sich die
  Debug-Ansicht automatisch für die hochgeladene PDF (ohne sie zu speichern).
  Inhalte können PII enthalten → nur für den angemeldeten Nutzer, nichts geht ins Log.

## [0.26.7] - 2026-07-02

### Added
- **Automatisches Backup.** TUIWatch legt jetzt einmal pro Woche ein vollständiges
  Backup-ZIP (Angebote inkl. Preisverlauf & Marker, Reisen inkl. PDF, gespeicherte
  Suchen) unter `/addon_config/backups/` ab — dieser Ordner übersteht auch eine
  Neuinstallation des Add-ons. Rotation über `auto_backup_keep` (Standard 5),
  abschaltbar über `auto_backup`. Wiederherstellen wie gehabt im Web-UI.
- Fehlende Options-Übersetzungen (DE/EN) für die Aktionscode-Einstellungen ergänzt.

## [0.26.6] - 2026-07-02

### Added
- **Preis-Einordnung zum 30-Tage-Schnitt.** Die Statistik-Zeile jeder Karte zeigt jetzt
  zusätzlich, wie der aktuelle Preis zum Durchschnitt der letzten 30 Tage steht
  (z. B. „8 % unter Ø 30 T", grün/rot, ab ±1 %) — hilft bei der Frage „jetzt buchen
  oder warten?". Auch als HA-Sensor-Attribut `avg_price_30d`.
- **Trend-Badge mit Prozentwert.** „↘ fällt / ↗ steigt" zeigt jetzt die Stärke der
  Tendenz (z. B. „↘ fällt −3,1 %").

## [0.26.5] - 2026-07-02

### Fixed
- **Preiskalender: Sparschwein höher gesetzt** (leicht oberhalb der Zellmitte, etwas
  kleiner/transparenter) — es verdeckte den Preis am unteren Zellrand.

## [0.26.4] - 2026-07-02

### Changed
- **User-Agent aktualisiert** (Chrome 124 → 139) für die TUI-API-Abrufe — reine
  Auffrischung; die offenen JSON-APIs brauchen keine Tarnung/Rotation.

## [0.26.3] - 2026-07-02

### Changed
- **Preiskalender: schöneres Sparschwein-Icon** (detailliertes Piggy-Bank statt des
  einfachen Symbols), grün eingefärbt, mittig hinter dem Text.

## [0.26.2] - 2026-07-02

### Added
- **Wochenüberblick listet Aktionscodes.** Die wöchentliche Zusammenfassung (Telegram &
  E-Mail) enthält jetzt die aktuellen öffentlichen TUI-Aktionscodes (Wert, Code, buchbar
  bis, Reisezeitraum).
- **Aktionscode-Button leuchtet/pulsiert**, wenn aktuell Codes verfügbar sind.

### Changed
- **Preiskalender: Sparschwein größer & mittig** (hinter dem Text, verdeckt Tag/Preis
  nicht). Zusätzlich lässt sich der Kalender jetzt **mit den Pfeiltasten ← / →** durch die
  Monate blättern (nicht nur per Maus).

## [0.26.1] - 2026-07-02

### Added
- **TUI-Aktionscode-Überwachung (🎟 Aktionscodes).** TUIWatch liest die **öffentlichen**
  Aktionscodes von tui.com (`/aktionscode/`) — **ohne Login, ohne Browser, ohne Captcha** —
  und meldet **neue** Codes (Telegram/HA). Angezeigt werden Wert (z. B. 150/250/300 €),
  „buchbar bis" und Reisezeitraum; erfasst werden myTUI-Codes (`ACMYTUI…`) und Codes ohne
  Konto (`SAVE…`). Dedup nach Wert (kein Spam durch tägliche Datumswechsel im Code),
  Wiederkehr wird erneut gemeldet. Optionen: `notify_aktionscodes`, `aktionscode_min`
  (nur ab Wert melden), `aktionscode_interval` (Standard 6 h). „Jetzt prüfen" im UI.
- Ersetzt den in 0.26.0 verworfenen MyTUI-Coupon-Login-Ansatz (Bot-Schutz/Captcha nicht
  zuverlässig automatisierbar); der zugehörige Code wurde vollständig entfernt.

## [0.26.0] - 2026-07-01

Version Bump, Revert Coupon Feature


## [0.25.17] - 2026-07-01

### Added
- **Preiskalender: Sparschwein-Icon am günstigsten Termin.** Der günstigste Termin
  insgesamt wird zusätzlich zur grünen Markierung mit einem kleinen Sparschwein-Icon
  (SVG) gekennzeichnet — auch in der Legende.

## [0.25.16] - 2026-07-01

### Added
- **„Meine Reisen": Kennzahl „Eigene Kosten".** Neben den Gesamtausgaben (Summe aller
  Reisepreise) zeigt eine neue Kachel den **eigenen Anteil** = je Reise Gesamtpreis
  geteilt durch die Anzahl Reisende, aufsummiert. Auch als Spalte in der Jahrestabelle.
  Die Kacheln „Reisen"/„Nächte" sind dafür kompakter.

## [0.25.15] - 2026-07-01

### Security
- **CodeQL (HIGH) im neuen Backup/Restore behoben.**
  - *SQL aus Nutzerquellen:* Beim Wiederherstellen wurde die Spaltenliste des
    `INSERT INTO offers` aus den Schlüsseln der Backup-Datei gebildet. Die Spalten kommen
    jetzt aus einer festen Code-Whitelist (`_OFFER_RESTORE_COLS`); Werte bleiben
    parametrisiert. Funktional identisch.
  - *Pfad aus Nutzerdaten (2×):* `_trip_pdf_path` validiert den Dateinamen nun zusätzlich
    gegen einen strikt begrenzten Zeichensatz (`[A-Za-z0-9._-]`, nur Basename), bevor ein
    Pfad gebaut wird — schließt Path-Traversal über `pdf_name` aus Backup/Import sicher aus.

## [0.25.14] - 2026-07-01

### Changed
- **Backup & Restore jetzt vollständig.** Das Backup war unvollständig (nur nackte
  Angebots-Eckdaten). Es umfasst nun als **ZIP**: alle Angebote **inkl. Preisverlauf**
  und Diagramm-Marker, **„Meine Reisen" inkl. der Original-PDFs** sowie die
  **gespeicherten Suchen**. Die Wiederherstellung akzeptiert die ZIP (altes JSON weiterhin
  möglich) und arbeitet **nicht-destruktiv** (Upsert per URL/Buchungsnummer/Name –
  nichts wird gelöscht oder doppelt angelegt). Reine Caches (Vergleich/Kalender) werden
  bewusst nicht gesichert (regenerieren automatisch).

## [0.25.13] - 2026-07-01

### Fixed
- **Preiskalender deckt die volle Spanne ab.** Der Kalender reicht jetzt vom aktuellen
  Monat bis deutlich über den Reisezeitraum hinaus (im Beispiel Juli 2026 bis Oktober
  2027) und öffnet im Reisemonat. Die TUI-Kalender-API liefert pro Aufruf nur ein
  begrenztes Fenster (~12 Monate ab Startdatum); wie die TUI-Seite selbst werden nun
  mehrere Abrufe ab fortlaufendem Startdatum zusammengeführt, statt in einem einzelnen
  Aufruf vorne oder hinten abzuschneiden.

## [0.25.12] - 2026-07-01

### Changed
- **Hotelsuche: „Exakt"-Checkbox aufgeräumt.** Das Nächte-Feld ist etwas breiter und
  die „Exakt"-Checkbox sitzt jetzt sauber rechts neben dem Label „Nächte" (statt
  darüber umzubrechen).

## [0.25.11] - 2026-07-01

### Fixed
- **Preiskalender öffnet im Reisemonat & deckt den gewählten Zeitraum ab.** Bei weit
  entfernten Reisen (z. B. Reisebeginn September 2027) startete der Kalender bei einem
  nahen Monat (Dezember 2026) und ließ sich nur bis Juni 2027 blättern – der eigentliche
  Reisemonat war unerreichbar. Ursache: Der Suchbereich der Kalender-API war fix auf
  „heute" verankert, die API liefert aber nur ein begrenztes Fenster ab dem Startdatum.
  Der Suchbereich wird jetzt am gewählten Reisezeitraum verankert (Vorlauf/Nachlauf um
  `startDate`/`endDate`), und der Kalender öffnet direkt im Reisemonat.

## [0.25.10] - 2026-07-01

### Added
- **Hotelsuche: „Exakt"-Checkbox.** Sucht Reisen mit einer Dauer, die exakt dem
  gewählten Zeitraum entspricht (TUI-nativ `duration=exact`; z. B. 01.07.–05.07. →
  4 Nächte). Bei aktivem Häkchen ist das Nächte-Feld gesperrt (die Dauer bestimmt
  TUI) und zeigt zur Info die Tagesdifferenz.
- **Hotelsuche: „Reset"-Button.** Setzt die Suchmaske auf die Standardwerte zurück
  (inkl. Reiseziel, Abflughafen, Datum, Nächte, Reisende und Filter).

### Changed
- **Hotelsuche: Plausibilitäts-Hinweis für die Nächte.** Passen die gewählten Nächte
  nicht in den Reisezeitraum (z. B. 01.07.–03.07. mit 5 Nächten), erscheint ein
  Live-Hinweis und beim Suchen zusätzlich ein Toast. Die Suche wird trotzdem
  ausgeführt.

## [0.25.9] - 2026-06-30

### Security
- **CodeQL (HIGH): SQL-Struktur nicht mehr aus request-nahen Daten ableiten.** Beim
  Reise-Import (`api_trip_import`) wurden die Spaltennamen für INSERT/UPDATE aus
  `row.keys()` gebildet. Obwohl alle Werte parametrisiert (`?`) waren, markierte CodeQL
  die aus Daten abgeleitete Query-Struktur. Spalten kommen jetzt aus einer festen
  Code-Konstante `_TRIP_COLUMNS` (Whitelist, exakte Reihenfolge); ein Assert stellt
  sicher, dass `row` keine unerwarteten Keys enthält. Funktional identisch.

## [0.25.8] - 2026-06-30

### Changed
- **PDF-Parser deutlich robuster gegen Layout-Änderungen.** Neue zentrale
  Vorreinigung (`_clean_text`) entfernt vor dem Parsen einmalig die wiederkehrenden
  Seiten-„Möbel" (Kopf-/Fußzeilen, Rechts-Boilerplate, `Seite X/Y`, wiederholte
  Tabellenköpfe), alleinstehende Fußnoten-Hochzahlen sowie die Punktelinien der
  „auf einen Blick"-Übersicht. Dadurch laufen die Feld-Regexes auf sauberem,
  lückenlosem Text — der häufigste Bruchgrund (eingeschobene Zeilen durch
  Seitenumbruch, z. B. nicht erkannte Rückflüge) entfällt. Künftige Eigenheiten
  werden an **einer** Stelle gepflegt statt in jeder Regex einzeln.

### Added
- **Golden-Test-Korpus** (`tests/fixtures/trips/`): vier echte, PII-bereinigte
  Buchungsbestätigungen (3 Layout-Generationen, 1–7 Reisende) mit erwartetem
  Parse-Ergebnis. Bricht TUI künftig das Format, zeigt der Test exakt, welches
  Feld kippt — gezielter Fix statt Raten.

## [0.25.7] - 2026-06-30

### Fixed
- **PDF-Import: Rückflug über Seitenumbruch.** Lag zwischen Zeit- und Streckenzeile
  eines Fluges ein kompletter Seitenumbruch (Footer + Folgeseiten-Kopf, z. B. bei
  Mallorca-Bestätigungen), wurde der Rückflug nicht erkannt. Der Parser überspringt
  jetzt Zwischenzeilen bis zur Streckenzeile. Zudem werden hochgestellte
  Fußnoten-Ziffern (z. B. „… (PMI) 3") aus Strecke/Flughafen entfernt.

### Added
- **Import-Hinweis bei unvollständiger Erkennung.** Werden beim PDF-Import wichtige
  Felder nicht (vollständig) erkannt (z. B. Hotel, Reisezeitraum, Gesamtpreis, Hin-/
  Rückflug), erscheint ein Hinweis-Toast und ein gelber Hinweisbalken in der
  Reise-Detailansicht mit der Liste der betroffenen Felder.

## [0.25.6] - 2026-06-30

### Added
- **Sortierung „Ort A–Z":** Neue Option im Sortier-Menü der Angebotsliste, die nach
  dem Reiseziel/Ort sortiert (z. B. „Kolymbia, Rhodos"). Angebote ohne Ort wandern ans
  Ende. Die Suche durchsucht den Ort bereits.

## [0.25.5] - 2026-06-30

### Changed
- **Flüge mit Wochentag:** In der Angebotsliste zeigen Hin- und Rückflug jetzt den
  Wochentag vor dem Datum, z. B. „Hin: **Mo** 03.05.2027, 13:30" / „Rück: **Fr**
  14.05.2027, 18:10". Erleichtert die Planung auf einen Blick.

## [0.25.4] - 2026-06-30

### Changed
- **Reisen-Statistik & Liste jetzt pro Person:** Der **€/Nacht**-Wert je Reise (Liste) sowie
  der **Ø €/Nacht** in der Gesamt- und Jahresstatistik werden **pro Person** ausgewiesen
  (Personen-Nächte = Nächte × Reisende). So sind Solo- und Gruppenreisen vergleichbar
  (z. B. Gruppenbuchung mit 7 Reisenden: 282,50 €/Nacht p. P. statt 1.977,50 € für die
  ganze Buchung). Labels mit „p. P." gekennzeichnet.

## [0.25.3] - 2026-06-30

### Fixed
- **PDF-Import:** Reisezeitraum (und damit **€/Nacht** sowie **€/Person/Nacht**) wurde nicht
  berechnet, wenn der Paket-Block die Status-Spalte direkt anhängt
  (`… – Paket (Unterkunft) bestätigt`). Betraf u. a. Buchungen mit mehreren Reisenden. Der
  Zeitraum/Hotel wird jetzt unabhängig vom Zusatztext erkannt; die Pro-Person-Berechnung
  (Division durch die Anzahl der Reisenden, 1–7) greift wieder.

## [0.25.2] - 2026-06-30

### Fixed
- **PDF-Import:** Der **Rückflug** wurde bei manchen Bestätigungen nicht erkannt, wenn die
  Status-Spalte („enthalten") als eigene Zeile zwischen Datums- und Zeitzeile steht. Der
  Flug-Parser überspringt solche Zwischenzeilen jetzt.

## [0.25.1] - 2026-06-30

### Added
- **Reisen-Datenbank:** Pro Buchung jetzt der **Reisepreis pro Nacht** (reiner
  Hotel-/Flug-/Transfer-Preis **nach Rabatt, ohne Extras**) — in der Liste je Reise und in
  der Detailansicht zusätzlich **€/Person/Nacht** (entspricht der „€/Nacht"-Spalte der
  Reisen-Übersicht).
- **Statistik pro Reisejahr** (Reisen, Nächte, Ausgaben, Ø €/Nacht) zusätzlich zur
  Gesamtstatistik.

## [0.25.0] - 2026-06-30

### Added
- **Reisen-Datenbank (PDF-Import):** Neuer Bereich **„🧳 Meine Reisen"** für **gebuchte**
  Reisen. Eine TUI-Reisebestätigung als **PDF** hochladen (oder per Drag & Drop) — die
  Eckdaten (Buchungsnummer, Reisende, Hotel, Zeitraum, Flüge, Extras, Rabatte, Zahlungen,
  Preise) werden ausgelesen. Die **PDF bleibt dauerhaft gespeichert** (unter `/data/trips`)
  und ist je Reise wieder **abrufbar** (öffnen/herunterladen). Reisen lassen sich jederzeit
  **löschen** (inkl. der gespeicherten PDF).
- **Übersichts-Statistik:** Anzahl Reisen, Summe Nächte, Gesamtausgaben und Ø €/Nacht.
- Re-Import derselben Buchungsnummer **aktualisiert** den bestehenden Eintrag (kein Duplikat).
- Der PDF-Parser liegt als eigenes Modul `tripparser.py` vor (für spätere Layout-Anpassungen)
  und ist tolerant gegenüber den bekannten TUI-Layout-Varianten sowie 1–7 Reisenden.

## [0.24.2] - 2026-06-30

### Changed
- **Bereits getrackte Hotels** lassen sich in der Suche jetzt **erneut tracken**: Der
  Button ist nicht mehr deaktiviert, sondern fügt das Hotel mit den **aktuellen
  Suchparametern** (z. B. anderer Zeitraum) als weiteres Angebot hinzu. Das „✓ getrackt"
  am Namen bleibt als Hinweis bestehen; nur exakt identische Angebote (gleiche URL) werden
  weiterhin abgelehnt.

## [0.24.1] - 2026-06-30

### Added
- **„💾 Änderungen speichern"** bei den gespeicherten Suchen: Eine geladene Suche lässt sich
  nach Anpassungen direkt überschreiben, ohne den Namen erneut eingeben zu müssen. Der
  Button ist nur aktiv, wenn eine gespeicherte Suche ausgewählt ist; „★ Speichern" legt
  weiterhin eine neue Suche (mit Namensabfrage) an.

## [0.24.0] - 2026-06-30

### Added
- **Globale Reiseziel-Suche:** Das Suchfeld im Reiseziel-Picker durchsucht jetzt **alle
  Ebenen** des TUI-Reiseziel-Baums. Tippt man z. B. „Kanarische Inseln", erscheint das Ziel
  direkt — ohne erst Spanien öffnen zu müssen. Die Treffer zeigen ihren Pfad
  (z. B. „— Spanien › Kanarische Inseln"). Grundlage ist ein flacher Index des kompletten
  Baums, der beim Start (und danach alle 14 Tage) im Hintergrund aufgebaut und in der
  Datenbank zwischengespeichert wird; manuell neu aufbaubar über `POST /api/destinations/reindex`.
- **Gespeicherte Suchen in der Datenbank:** Favoriten-Suchen liegen nicht mehr nur im
  Browser-Cache, sondern in der Add-on-Datenbank — damit sind sie **geräteübergreifend**
  verfügbar (gleiche Liste auf Handy, Tablet, PC).

## [0.23.1] - 2026-06-29

### Fixed
- **HolidayCheck-Link** trifft jetzt das richtige Hotel: Statt der HolidayCheck-Suchseite
  (die den Begriff nicht zuverlässig auswertete) öffnet der Link eine Google-Suche
  `site:holidaycheck.de <Hotel> <Region>` — der erste Treffer ist die passende
  HolidayCheck-Hotelseite.

## [0.23.0] - 2026-06-29

### Added
- **HolidayCheck-Link:** Die Bewertungszeile (Karte und E-Mail) ist jetzt anklickbar und
  öffnet die HolidayCheck-Hotelsuche zum Hotel (Name + Region). Einen exakten Deep-Link
  liefert TUI nicht — daher die Namenssuche, die zuverlässig beim Hotel landet.

## [0.22.1] - 2026-06-29

### Changed
- **Verlauf-Marker:** größere Trefferzone für den Mouseover — der Tooltip rastet auf den
  nächstgelegenen Marker ein und erscheint sofort beim Annähern (statt nur exakt auf dem
  Fähnchen).

## [0.22.0] - 2026-06-29

### Added
- **Änderungs-Marker im Verlauf-Diagramm:** Wichtige Eingriffe werden als Fähnchen auf
  der Zeitachse markiert — **Zimmerwechsel**, **gebuchter Preis**, **Wunschpreis** und
  **Zurücksetzen**; **Mouseover** zeigt Datum + Beschreibung.
- **Hotelsuche:** Nach **Tracken** eines Treffers öffnet sich direkt die **Zimmerauswahl**
  des neuen Angebots — so lässt sich gleich die gewünschte Kategorie festlegen.

## [0.21.0] - 2026-06-29

### Added
- **Buchungscodes & Flugnummern** je Angebot: **TUI-Buchungscode** (z. B. `LPA21031`),
  **Zimmer-Buchungscode** (z. B. `DZX1A`) und **GIATA-Hotel-ID** werden in der Karte und
  in der E-Mail angezeigt; die **Flugnummern** (z. B. `X3 2168`) stehen in den Hin-/Rück-
  Flugzeilen. Auch als Sensor-Attribute `booking_code`/`room_booking_code`.

## [0.20.4] - 2026-06-29

### Changed
- **Verlauf-Diagramm** zoomt jetzt auf den echten Preisverlauf (mit etwas Polster) —
  kleine Änderungen (z. B. −6 €) sind klar erkennbar. Die gestrichelte
  Vergleichspreis-Linie wurde entfernt (streckte die Achse); der Vergleichspreis steht
  weiter in der Tabellenspalte „Vergleich". Wunsch- und Buchungspreis-Linie bleiben.
- **Kartenliste:** der kleine Inline-Verlaufs-Chart (Spark) wurde entfernt — übersichtlicher
  und platzsparender; der volle Verlauf bleibt über den Button **Verlauf**.
- **Suche:** Reihenfolge der Verpflegungs-Filter zu **AI, VP, HP, Frühstück, Ohne**.

## [0.20.3] - 2026-06-29

### Added
- **Sammelaktion „E-Mail":** Die markierten Angebote lassen sich jetzt direkt als E-Mail
  versenden (Empfänger wird abgefragt, Vorbelegung wie beim normalen Versand). Es werden
  nur die ausgewählten (aktiven) Angebote gesendet.

## [0.20.2] - 2026-06-29

### Fixed
- **Suche markierte archivierte Angebote als „getrackt"**: Ein archiviertes Hotel
  erschien in der Regionssuche weiter als „✓ getrackt" und ließ sich nicht erneut
  aufnehmen. Jetzt zählt nur noch **aktiv** Getracktes (Archiv ausgenommen).

### Added
- **Suchfeld in der Region-Trefferliste**: filtert die angezeigten Treffer sofort nach
  Hotelname, Ort/Land und Verpflegung (Anzahl „X von N").

## [0.20.1] - 2026-06-29

### Fixed
- **Verpflegungsfilter in der Suche** wirkte nicht: HP/VP/Frühstück nutzten ungültige
  Codes (`HP`/`VP`/`F`) und wurden ignoriert — dadurch erschienen z. B. bei „Frühstück"
  auch „Ohne Verpflegung"-Treffer. Jetzt korrekte API-Codes (`HB`/`FB`/`BB`); `AI`
  unverändert. Die Filter schließen die jeweilige **„Plus"-Variante** automatisch ein
  (AI = inkl. „AI Plus/laut Programm", HP = inkl. Halbpension Plus, VP = inkl.
  Vollpension Plus).

### Added
- Verpflegungsfilter **„Ohne"** (ohne Verpflegung) ergänzt.

## [0.20.0] - 2026-06-29

### Added
- **Zimmerauswahl pro Angebot:** Neuer Button **„Zimmer"** zeigt die wählbaren
  Zimmerkategorien (Name + Verpflegung + Preis pro Person + Aufpreis zum günstigsten).
  Standard bleibt das **günstigste** Zimmer; per **„tracken"** lässt sich eine bestimmte
  Kategorie fixieren (dann wird deren Preis verfolgt), **„Details ↗"** öffnet das Zimmer
  mit Fotos/Beschreibung auf tui.com, **„Günstigstes automatisch"** hebt die Festlegung
  auf. Technisch über `roomTypeOpCodes` in der Angebots-URL (Quelle: Offer-API, gruppiert
  nach Zimmercode).

## [0.19.2] - 2026-06-29

### Fixed
- **Poll-Fehler `name 'date' is not defined`** behoben: `date` war in app.py nicht
  importiert, wodurch der Wochenüberblick (bei aktivem `digest_enabled`) bei jeder
  automatischen Prüfung abbrach.

## [0.19.1] - 2026-06-28

### Changed
- **Karten-Layout** mit Hotelbild aufgeräumt: das Bild sitzt jetzt **unter dem Preis**
  (rechte Spalte) statt links, und **Wunschpreis + gebuchter Preis** stehen
  **nebeneinander** (umbrechend auf schmalen Bildschirmen).

## [0.19.0] - 2026-06-28

### Added
- **Gebuchter Preis:** Pro Angebot lässt sich der **tatsächlich gezahlte Preis**
  hinterlegen (Feld „📌 Gebuchter Preis"). Das Tracking läuft weiter; angezeigt wird
  „seit Buchung ±X €" und im Preis-Diagramm eine eigene Linie. **„Günstiger als
  gebucht"-Alarm** (HA/Telegram) meldet, wenn der Preis später deutlich darunter fällt
  (Optionen `notify_booked_drop`, `booked_drop_min_diff`); nur bei neuen Tiefstwerten,
  neustart-fest. Auch als Sensor-Attribute `booked_price`/`booked_diff`.
- **Hotelbild bei getrackten Angeboten:** Beim Tracken aus der Suche wird das Bild
  übernommen; bei per URL hinzugefügten Angeboten wird es beim ersten Check einmalig über
  eine Regionssuche ermittelt (Quelle: TUI-Such-API). Anzeige als Thumbnail in der Karte;
  Sensor-Attribut `image`.

## [0.18.1] - 2026-06-28

### Fixed
- **Fluggesellschaften-Dropdown**: Checkboxen waren verrutscht (die globale Eingabefeld-
  Regel hat sie auf volle Breite gezogen) und das Panel saß versetzt — beides korrigiert
  (Checkboxen feste Größe, Panel linksbündig unter dem Feld).

### Added
- **Suche im Reiseziel-Picker**: Textfeld zum Filtern der aktuell angezeigten Liste
  (z. B. Land eintippen, dann hineinblättern).

## [0.18.0] - 2026-06-28

### Added
- **Hotelsuche: optionaler Fluggesellschaften-Filter** — Dropdown mit Mehrfachauswahl
  (leer = alle). Die Auswahl geht in die Suche und in das getrackte Angebot (dann wird
  der Preis nur mit diesen Airlines verfolgt). Kuratierte Airline-Liste über
  `GET /api/airlines`.

### Changed
- **Such-Defaults**: Sterne ≥ **3** und Weiterempfehlung ≥ **80 %** sind in der Maske
  vorbelegt (jederzeit änderbar).

## [0.17.0] - 2026-06-28

### Added
- **Regressionstests fürs Parsing** (`tuiwatch/tests/`, pytest): prüfen offline gegen
  echte, reduzierte TUI-API-Antworten, dass die Auswertung (Preis, Rabatt, Nächte,
  Verpflegung, Reisende, Flug, Rückreisedatum, Bewertung, Region, Suche, Kalender,
  Reiseziele, Abflughäfen) und die URL-/Helfer-Logik korrekt bleiben. CI-Workflow
  `test-tuiwatch.yml` führt sie bei Änderungen an `tuiwatch/*.py` aus.

### Changed
- `scraper.py` importiert **playwright nur noch lazy** (erst im Browser-Fallback) — das
  Modul ist damit ohne playwright importierbar (Voraussetzung für die Tests; erster
  Schritt zur Verschlankung des Images).

## [0.16.1] - 2026-06-28

### Fixed
- **Übersetzungen** für die neuen Optionen `notify_api_errors`, `digest_enabled` und
  `digest_weekday` (DE + EN) ergänzt — im HA-Konfig-UI wurden zuvor die rohen
  Schlüsselnamen angezeigt.

## [0.16.0] - 2026-06-28

### Added
- **API-Ausfall-Alarm**: Fällt im Selbsttest ein *kritischer* TUI-Endpunkt aus (z. B.
  weil TUI die API geändert hat), meldet TUIWatch das über HA/Telegram und gibt
  Entwarnung, sobald wieder alles läuft. Zustand übersteht Neustarts. Abschaltbar über
  `notify_api_errors`.
- **Selbsttest läuft automatisch ~1×/Tag** und jeweils **vor den Preisprüfungen**, damit
  die Footer-Ampel aktuell bleibt und ein API-Problem erkannt wird, bevor die Abfragen
  daran scheitern.
- **Wochenüberblick (Digest)**: optionale wöchentliche Zusammenfassung per Telegram/E-Mail
  (größte Rückgänge, neue Tiefstwerte, Angebote unter Wunschpreis). Aktivierung über
  `digest_enabled` + `digest_weekday` (1 = Mo … 7 = So); Sofortversand über den Button
  **„📊 Wochenüberblick"**.
- **Trend-Hinweis** je Angebot (↘ fällt / ↗ steigt / → stabil) aus dem bisherigen
  Preisverlauf — als kleines Badge neben der Preisänderung.
- **Sammelaktionen**: Angebote per Checkbox auswählen und gemeinsam **prüfen,
  archivieren oder löschen** (Aktionsleiste erscheint bei Auswahl).

## [0.15.0] - 2026-06-28

### Added
- **API-Selbsttest**: prüft beim Start des Add-ons und manuell, ob alle genutzten
  TUI-Endpunkte (Preis/Angebot, Hotelsuche, Reiseziele, Abflughäfen, Preiskalender,
  Bewertung, Breadcrumb) noch erwartungsgemäß antworten. Ergebnis im **Footer** als
  Ampel (grün/gelb/rot); Klick öffnet die Detailliste mit „Erneut prüfen".
- **Trackerliste nach Reisebeginn sortierbar** (neue Sortieroption; Angebote ohne
  festes Datum ans Ende).

### Changed
- **Günstigerer-Termin-Alarm** kommt nur noch bei einem **wirklich neuen Tiefstwert**
  (anderer Abreisetag oder nochmals tieferer Preis) und übersteht Add-on-Neustarts
  (persistenter Dedup) — keine Wiederholungen mehr bei jeder Prüfung. Abschaltbar über
  `notify_cheaper_date`.
- **Suche: Datumspicker** — „bis" springt automatisch auf „von" und kann nicht mehr
  vor dem Abreisedatum liegen.

### Fixed
- **Nächte-Vergleich für aus dem Kalender getrackte Termine**: das feste Reisefenster
  (genau N Nächte) wird beim Vergleich passend geweitet (`endDate = startDate + Dauer`),
  sodass längere Dauern nicht mehr fälschlich als „nicht abrufbar" erscheinen.

## [0.14.1] - 2026-06-28

### Fixed
- **Kalender-Icon der Datumsfelder im Dark Mode sichtbar** (aufgehellt); im Light Mode
  unverändert. Klick aufs Feld öffnet weiterhin den Kalender, Direkteingabe bleibt möglich.

## [0.14.0] - 2026-06-28

### Added
- **Suche: „Nur Direktflug"-Filter** — zeigt nur Angebote ohne Zwischenstopp
  (Such-API-Parameter `stopOver=0`; wird auch in getrackte Angebote übernommen).

### Changed
- **Fortschrittsanzeige statt Sanduhr**: Nächte-Vergleich zeigt einen echten
  Fortschrittsbalken (geprüfte Dauern X/N); Pro-Person-Vergleich, Suche und Preiskalender
  zeigen einen animierten Balken statt des ⏳-Symbols.
- Suche: Datumsfelder öffnen den Kalender beim Klick aufs ganze Feld; „Suchen"-Button
  rechtsbündig; Filter **„nur Veranstalter TUI"** kürzer als **„TUI"** beschriftet
  (mit erklärendem Tooltip).

## [0.13.0] - 2026-06-28

### Added
- **Eigene Suchmaske mit Reiseziel-Picker** — kein URL-Kopieren mehr nötig: **Reiseziel**
  per Drilldown (Land → Region → Insel) wählen, **Abflughafen** (TUI-Liste), **Zeitraum
  von–bis + Nächte**, **Reisende** und die Filter setzen → **Suchen**. Nutzt die offenen
  TUI-APIs `search-destination` (Regionen/Unterregionen) und `search-departure-airport`.
- **Such-Favoriten**: komplette Maskeneingaben unter einem Namen speichern und wieder
  laden (Dropdown + „★ Speichern" / „Löschen").
- **Sortierung der Trefferliste**: Preis, Preis/Nacht, Weiterempfehlung, Sterne.
- Die bisherigen Wege (TUI-URL einfügen, „Region" aus einem Angebot) bleiben erhalten.

## [0.12.0] - 2026-06-28

### Added
- **Regionssuche direkt aus einem Angebot**: neuer Button **„Region"** je aktivem
  Angebot listet weitere Hotels **derselben Region** (z. B. Gran Canaria) für dieselben
  Reisedaten/Dauer/Reisende/Abflughafen — ohne URL-Einfügen. Die Region kommt aus der
  Angebots-URL (`regionGiataIds`) oder per Breadcrumb über die giataId. Veranstalter und
  Verpflegung des Angebots werden als Filter **vorbelegt** (änderbar), Sterne/
  Weiterempfehlung optional.

### Changed
- **Such-Dialog breiter** (übersichtlichere Trefferliste).

## [0.11.0] - 2026-06-28

### Added
- **Hotelsuche** über **🔍 Hotels suchen**: eine TUI-Such-/Region-URL (mit
  `regionGiataIds`) einfügen → TUIWatch listet alle passenden Hotels der Region mit
  **Sternen, Ort, HolidayCheck-Weiterempfehlung, Verpflegung, Nächten und Preis p. P.**
  Filter direkt im Add-on: **nur Veranstalter TUI**, **Verpflegung** (AI/HP/VP/Frühstück),
  **Sterne ≥** und **Weiterempfehlung ≥ %**. Je Treffer **Tracken**/**Öffnen**, dazu
  **Alle tracken**. Abflughafen/Zeitraum kommen aus der eingefügten URL. Nutzt den neuen
  TUI-Such-Endpoint `hotel-offer-cards/v2/search` (siehe SCRAPING.md).

## [0.10.2] - 2026-06-28

### Fixed
- **Kein unnötiger (langsamer) Browser-Fallback bei „kein Angebot".** Liefert die
  Offer-API **HTTP 400/404/422** (z. B. beim Nächte-Vergleich für eine Dauer ohne Flüge),
  wird das jetzt als gültige Leermenge „Kein Angebot" behandelt — vorher wurde
  fälschlich der minutenlange Chromium-Fallback gestartet. Echte Serverfehler (5xx) /
  Netzwerkfehler lösen weiterhin den Fallback aus.

## [0.10.1] - 2026-06-28

### Fixed
- **Nächte-Vergleich: falsche Preise bei nicht buchbaren Dauern.** Bei Bereichs-Dauern
  wie `7-` lieferte TUI für nicht verfügbare Dauern (z. B. 8–10 Nächte) ersatzweise das
  nächstliegende Angebot (das 7-Nächte-Paket) zurück — diese Zeilen zeigten denselben
  Gesamtpreis und nur eine heruntergerechnete €/Nacht. Es wird nun geprüft, ob die
  **tatsächliche Reisedauer** der angefragten entspricht; weicht sie ab, erscheint
  korrekt „nicht abrufbar".

### Changed
- **Kleinere Buttons** in der Angebots-Fußzeile (kompaktere Schrift/Abstände), damit die
  Aktionsleiste weniger Platz braucht.

## [0.10.0] - 2026-06-28

### Added
- **Nächte-Vergleich**: neuer Button „Nächte" je Angebot öffnet einen Dialog, in dem
  sich per **− / +** eine Spanne einstellen lässt (Default 3, max ±7). Es werden live
  die Preise für **kürzere und längere Reisedauern** abgefragt (z. B. bei 10 Nächten:
  7–9 und 11–13) und als Tabelle gezeigt: **Preis p. P., € pro Nacht, Gesamt, Differenz**.
  Günstigste Zeile grün, aktuelle Dauer markiert; Dauern ohne Flug/Angebot erscheinen
  als „nicht abrufbar". Das Ergebnis wird gespeichert (mit „Neu abfragen").

## [0.9.1] - 2026-06-28

### Fixed
- **Preiskalender-Klick erzeugte ein ungültiges Datum** (HTTP 400 auf tui.com): Es wurde
  `startDate` = `endDate` = angeklickter Tag gesetzt, sodass der Reisezeitraum z. B.
  „21.05.2027 – 21.05.2027, 10 Nächte" lautete. Jetzt wird `endDate = Anreise + Nächte`
  berechnet (Hin- bis Rückreise), passend zur Reisedauer. Gilt für Links- und Rechtsklick
  (Termin öffnen / als neues Angebot speichern). Die Dauer kommt aus dem Preiskalender
  (`duration`).

## [0.9.0] - 2026-06-28

### Added
- **Archiv**: Angebote können archiviert werden — als Überblick über ältere/abgelaufene
  Reisen, ohne dass weiter live abgefragt wird.
  - **Automatisch**: sobald das Rückreisedatum in der Vergangenheit liegt, wandert ein
    Angebot ins Archiv (es ist ohnehin nicht mehr buchbar/abfragbar).
  - **Manuell**: Button „Archivieren" je Angebot (z. B. wenn ausgebucht / nicht mehr
    verfügbar) bzw. „Reaktivieren" zum Zurückholen.
  - Archivierte Angebote sind über den Schalter **„Archiv"** oben einblendbar (eigener
    Abschnitt, gedämpft dargestellt) und werden im Poller/„Alle prüfen", in der
    Übersicht (eigener Zähler + `archived_offers` am Summary-Sensor) und im E-Mail-Versand
    ausgenommen. Backup/Wiederherstellen nimmt den Archiv-Status mit.

### Fixed
- **Pauschalreise inkl. Transfer**: Offer-Abfrage nutzt jetzt `transferIncluded=true`
  (vorher `false`) — passend zur Buchung auf tui.com. Ein in der Original-URL gesetzter
  Wert hat weiterhin Vorrang.

## [0.8.1] - 2026-06-28

### Added
- **Preiskalender → Rechtsklick** auf einen Tag speichert genau diesen Termin als
  **neues, eigenständiges Angebot** (mit fixiertem Datum) und prüft ihn sofort. Linksklick
  öffnet den Termin weiterhin auf tui.com.

## [0.8.0] - 2026-06-28

### Added
- **E-Mail-Versand**: Button „Als E-Mail senden" verschickt alle Angebote als optisch
  aufbereitete HTML-Mail. Empfänger wird vor dem Senden eingegeben (Vorbelegung aus
  `smtp_to`/zuletzt genutzt). SMTP über neue Optionen `smtp_host/port/user/password/
  from/to/tls` (Muster wie MyPage). Footer mit Hinweis + GitHub-Link.
- **Backup & Wiederherstellen**: getrackte Angebote als JSON sichern und importieren
  (überspringt Duplikate, prüft neue sofort).
- **Übersicht** über der Liste: Anzahl Angebote, günstigstes Angebot, Anzahl unter
  Wunschpreis, pausierte — plus HA-**Summary-Sensor** `sensor.tuiwatch_uebersicht`
  (Wert = günstigster Preis; Attribute: günstigstes Angebot, Gesamtzahl, unter Wunschpreis).
- **Preiskalender-Heatmap**: Tage je nach Preis eingefärbt (grün→rot); **Klick auf einen
  Tag öffnet genau diesen Termin auf tui.com**.

## [0.7.2] - 2026-06-28

### Added
- **Ort öffnet Google Maps**: Klick auf den Ort (📍) öffnet das Hotel in Google Maps
  (Suchanfrage Hotelname + Ort; TUI liefert keine Koordinaten).

## [0.7.1] - 2026-06-28

### Changed
- **Konsole deutlich gesprächiger**: Prüfungen zeigen jetzt Name, Preis pro Person,
  Gesamtpreis, Verfügbarkeit und Quelle (API/Browser) sowie Preisänderungen. Zusätzlich
  protokolliert: Hinzufügen, Umbenennen, Pausieren/Fortsetzen, Wunschpreis, manuelle
  Prüfung, Vergleich-/Kalender-Start und gesendete Benachrichtigungen/Alarme.
- **Fehler werden rot markiert** (Log-Level ERROR), echte Ausfälle deutlich sichtbar;
  Ausweichen auf den Browser-Fallback erscheint gelb (WARNING). Verbose-Log zeigt die
  API-URLs zusätzlich.

## [0.7.0] - 2026-06-28

### Added
- **Tracking pausieren** je Angebot (ohne löschen): pausierte Angebote werden bei der
  automatischen Prüfung und „Alle prüfen" übersprungen; manuelles „Prüfen" bleibt
  möglich. Badge „⏸ pausiert" + abgedimmte Karte.
- **CSV-Export** der Preishistorie (Button im Verlauf-Fenster) — mit Excel-tauglichem
  Format (Semikolon, UTF-8-BOM).
- **PWA / installierbar**: Manifest, Service Worker und App-Icons (192/512) — TUIWatch
  lässt sich als App installieren (am besten über Direktzugriff/Reverse-Proxy).
- **Gesamtpreis** zusätzlich zum Preis pro Person (bei mehreren Reisenden) in der Karte
  und als HA-Sensor-Attribute `total_price` / `travellers`.

## [0.6.1] - 2026-06-28

### Fixed
- **Preiskalender bei Dauer-Bereichen** (z. B. `duration=7-` oder `9-12`) lieferte nichts.
  Der Kalender braucht eine einzelne Dauer — es wird jetzt die untere Zahl verwendet
  (wie auf der TUI-Seite).

### Changed
- **Ausführliches Logging** zeigt jetzt auch die **API-Abrufe (URLs) und Ergebnisse**
  in der Konsole (Offer-/Kalender-/Bewertungs-/Ort-Abruf), wenn `verbose_log` an ist.

## [0.6.0] - 2026-06-28

### Added
- **Günstigerer-Termin-Alarm**: Meldung (HA/Telegram), wenn der Preiskalender einen
  anderen Abreisetag deutlich günstiger zeigt als dein getrackter Preis (Schwelle per
  `cheaper_date_min_diff`, Standard 50 €). Aktualisiert nebenbei den Kalender-Cache.
- **Ausverkauft-/Fehler-Alarm**: Meldung, wenn ein Angebot mehrmals in Folge kein
  Ergebnis liefert (ausgebucht/URL veraltet), plus Entwarnung, sobald es wieder klappt.
  Optionen `notify_cheaper_date`, `cheaper_date_min_diff`, `notify_errors`.
- **Angebot umbenennen** direkt im UI (✎ neben dem Namen).
- **Sortierung** der Angebotsliste: Hinzugefügt, Preis, größte Preisänderung,
  Bewertung, Name.
- **Diagramm-Extras**: Wunschpreis-Linie, Vergleichspreis-Verlauf und grüne
  Marker für Preisrückgänge im Verlaufs-Diagramm.

## [0.5.1] - 2026-06-28

### Added
- **Zurücksetzen je Angebot**: Button löscht den kompletten Preisverlauf sowie
  Vergleichs-/Kalender-Cache und startet sofort eine frische Erstabfrage — das Tracking
  beginnt wieder bei „null". Das Angebot selbst (URL, Name, Wunschpreis) bleibt erhalten.

## [0.5.0] - 2026-06-28

### Added
- **Hotelbeschreibung als PDF**: Link je Angebot (öffnet das offizielle TUI-Hotel-PDF).
  Wird aus den Angebotsdaten gebaut und auch als HA-Sensor-Attribut `hotel_pdf` bereitgestellt.

### Changed
- **Preiskalender zeigt jetzt die volle buchbare Spanne** (heute bis ~12–14 Monate,
  inventarabhängig) statt nur des gewählten Zeitraums ±7 Tage — durch alle verfügbaren
  Monate blätterbar; der gewählte Zeitraum bleibt hervorgehoben.

## [0.4.1] - 2026-06-28

### Added
- **Ort/Region je Angebot** (z. B. „Playa del Ingles, Gran Canaria") — wird aus dem
  TUI-Breadcrumb gelesen, in der Karte unter dem Hotelnamen angezeigt, in die
  Schnellsuche aufgenommen und als HA-Sensor-Attribute ergänzt (`location`, `region`,
  `country`).

## [0.4.0] - 2026-06-28

### Added
- **Preiskalender** je Angebot (Button „Kalender"): Monats-Grid mit dem günstigsten
  Preis pro Abreisetag (wie auf tui.com). Markiert den günstigsten Termin (grün) und
  den günstigsten Termin **in deinem gewählten Zeitraum** sowie Tage außerhalb des
  Zeitraums (gedimmt); Monatsnavigation. Wird wie der Vergleich **gespeichert**
  (Zeitstempel + „Neu abfragen"). Respektiert alle Filter der Original-URL.

## [0.3.3] - 2026-06-28

### Fixed
- **Falscher Preis/falsche Verpflegung bei mehreren Verpflegungsarten**: Der
  JSON-Abruf übernahm nicht alle Filter der Original-URL — u. a. `boardTypes`,
  `operators`, `roomTypes`, `viewTypes` fehlten. Dadurch konnte die API ein anderes
  (billigeres) Angebot liefern, z. B. Halbpension statt „Alles Inklusive". Jetzt
  werden **alle Filter der Original-URL** durchgereicht, und die Verpflegungs-Codes
  werden korrekt ins API-Schema übersetzt (`AI` → `GT06-AI`).

## [0.3.2] - 2026-06-28

### Added
- **Schnellsuche**: Suchfeld über der Angebotsliste filtert die geladenen Angebote
  sofort nach Hotel, eigenem Namen, Ziel/Abflughafen und Reise-Details.

## [0.3.1] - 2026-06-28

### Changed
- **Pro-Person-Vergleich wird jetzt gespeichert** (in der Datenbank). Beim Öffnen
  wird das gespeicherte Ergebnis sofort angezeigt — kein unnötiger neuer Abruf mehr.
  Mit **Zeitstempel** („Abgefragt: …") und Button **„Neu abfragen"** für eine
  Aktualisierung auf Wunsch.

## [0.3.0] - 2026-06-28

### Changed
- **Preisabruf jetzt über die offene TUI-JSON-API** statt Seiten-Rendering — rund
  **0,5 s statt 30–60 s**, deutlich robuster (kein HTML-/Text-Parsing). Der
  Headless-Chromium-Scraper bleibt als **automatischer Fallback**, falls die API mal
  nicht erreichbar ist. Der eingegebene Reisezeitraum wird respektiert; getrackt wird
  das per `cheapest`-Flag markierte günstigste Angebot.
- Genauere Daten „gratis" aus der API: exakter Streichpreis/Rabatt, strukturierte
  Flüge (Datum/Zeit/Airline/Stopps/Route) und zuverlässige Verfügbarkeit.

### Added
- **Hotel-Sterne & HolidayCheck-Bewertung** (Ø-Note /6, Anzahl Bewertungen,
  Weiterempfehlung %) in der Karte und als HA-Sensor-Attribute (`stars`, `rating`,
  `rating_count`, `recommendation`).
- **„Kostenlos stornierbar"-Badge** (aus `cancellationType`) in der Karte und als
  Sensor-Attribut `cancellation`.

## [0.2.0] - 2026-06-28

### Added
- **Pro-Person-Vergleich**: Button „Vergleich" am Diagramm öffnet einen Live-Vergleich
  des Preises pro Person für die aktuelle Reisendenzahl gegenüber 2 Personen (bei
  aktuell 2 → 2 ↔ 1). Tabelle mit Preis p. P., Gesamt und Differenz; günstigster
  Preis pro Person grün hervorgehoben. Rein on-demand — nichts wird gespeichert.
- **Einzelzimmer-Riegel**: Bei Einzelzimmer-Angeboten („Einzelzimmer"/„Single Room")
  wird kein Vergleichs-Button angezeigt (2-Personen-Abruf nicht möglich).
- Robuster Vergleichs-Abruf: schlägt der feste Zimmercode für eine andere Belegung
  fehl, wird einmalig ohne `roomTypeOpCodes` erneut versucht.

## [0.1.6] - 2026-06-28

### Fixed
- **Neustart löste sofort eine Komplettabfrage aus**, auch wenn das Prüfintervall noch
  nicht erreicht war. Der Poller arbeitet jetzt **fälligkeitsbasiert**: ein Angebot
  wird erst wieder geprüft, wenn seit seinem letzten Check (über Neustarts hinweg) das
  Intervall verstrichen ist.

## [0.1.5] - 2026-06-28

### Added
- **Favicon** (TUI-Flugzeug-Icon) in Web-UI und Login-Seite.
- **AppArmor-Profil** (`apparmor.txt`, `tuiwatch_addon`) — schränkt das Add-on ein;
  Chromium-konform (inkl. `/dev/shm`).
- **Telegram-Startmeldung**: ist Telegram konfiguriert, kommt beim Start eine kurze
  Statusnachricht („TUIWatch gestartet — N Reisen geladen").

### Fixed
- **Preisdiagramme flackerten** alle paar Sekunden: das UI rendert jetzt nur noch bei
  tatsächlich geänderten Daten neu, statt bei jedem 5-Sekunden-Poll die Canvas neu zu
  zeichnen.

## [0.1.4] - 2026-06-27

### Added
- **Benachrichtigungen** bei Preisänderung und erreichtem Wunschpreis — über
  **Home Assistant** (persistent_notification) und/oder **Telegram** (Bot-Token +
  Chat-ID). Optionen: `notify_ha`, `notify_price_change`, `telegram_bot_token`,
  `telegram_chat_id`.
- **Wunschpreis (Zielpreis) pro Angebot** — im UI eingebbar; wird der Preis ≤ Wunsch,
  kommt eine Benachrichtigung. Auch als Sensor-Attribut `target_price`.
- **Statistik je Angebot**: niedrigster/höchster/Durchschnittspreis + „Bestpreis"-Badge
  (UI) sowie Sensor-Attribute `min_price`, `max_price`, `avg_price`.

### Changed
- **Robusterer Abruf**: bis zu 2 Versuche bei Fehlschlag; bestätigter Gesamtpreis nach
  Verfügbarkeitsprüfung; die Haupt-Angebotskarte wird zuverlässiger getroffen
  (keine „Empfehlungs"-Karte).

### Security
- Technische Exception-Texte werden nicht mehr im UI/Sensor angezeigt, sondern nur
  noch ins Log geschrieben (generische Meldung nach außen).

## [0.1.3] - 2026-06-27

### Changed
- **Getrackt wird jetzt der konkrete „Günstigster Preis"** (erste Angebotskarte,
  z. B. 1.978 €) statt des unverbindlichen „ab"-Lockpreises der Dein-Angebot-Box.
  Genauer und buchungsnah.

### Added
- **Flugdetails**: Hin- und Rückflug (Datum, Uhrzeit, Airline, Direkt/Umstieg)
  sowie Zimmer und Abflughafen werden ausgelesen, in der Karte angezeigt und als
  HA-Sensor-Attribute (`flight_outbound`, `flight_return`, `room`,
  `departure_airport`) gespeichert.
- **Verfügbarkeitsprüfung**: TUIWatch klickt „Verfügbarkeit prüfen" und erfasst,
  ob das Angebot verfügbar ist. Anzeige als Badge (✓/✗) und als HA-Sensor-Attribut
  `available` (true/false).

## [0.1.2] - 2026-06-27

### Added
- **Home-Assistant-Sensoren**: je Angebot ein Sensor `sensor.tuiwatch_<hotelname>`
  (bei gleichem Hotelnamen `_2`, `_3` …). Wert = aktueller Preis in €, bei Fehler
  `unavailable`. Attribute u. a. `description` (Reise-Eckdaten), `hotel`, `old_price`,
  `discount`, `last_checked`, `url`. Per Option `ha_sensors` abschaltbar.
  Verwaiste Sensoren werden automatisch entfernt.
- **Übersetzungen der Add-on-Konfiguration** (DE/EN) für die HA-Optionsseite.

## [0.1.1] - 2026-06-27

### Fixed
- **Konsole leer hinter Ingress**: Die Konsole hängte beim Aufruf von `/api/console`
  den Ingress-Pfad nicht an (G war nicht über `window` erreichbar) → 401, keine
  Ausgabe. `G` wird jetzt an `window` gehängt, sodass der korrekte Ingress-Pfad
  verwendet wird.

## [0.1.0] - 2026-06-27

### Added
- Erste Version: **TUIWatch — Reisepreis-Tracker** für TUI-Pauschalreisen
- Beliebig viele TUI-Angebots-URLs verfolgen (URL von tui.com einfügen)
- Preis-Auslesen per Headless-Chromium (Playwright) — liest die „Dein Angebot"-Box
- Speichert den Preisverlauf in SQLite und zeigt ihn als Diagramm
- Anzeige von aktuellem Preis, Vergleichspreis, Rabatt und **Delta** (gestiegen/gefallen)
- Automatischer Hotelname (`Riu Papayas`) und Reise-Eckdaten als Beschreibung
- Periodische Prüfung (Standard alle 6 h) + manuelles „Prüfen" / „Alle prüfen"
- Versteckte Konsole per Doppelklick auf das Logo (Hintergrund-Logs)
- Login-Schutz beim Direktzugriff; hinter HA-Ingress automatisch authentifiziert
- Oberfläche auf Deutsch
