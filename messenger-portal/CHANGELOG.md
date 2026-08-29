# Changelog – MessengerPortal

## [1.2.20] - 2026-08-29
- Das Portal erreicht die Messenger-Add-ons jetzt über ihren **Container-Hostnamen** (z. B. `424ccef4-whatsapp`) statt über den HA-Host und dessen veröffentlichten Port (neu: `hassio_api: true`). Der Hash davor ist der des Repositories, unterscheidet sich pro Installation und ist deshalb nicht fest verdrahtet
- Der Name wird zweistufig ermittelt: `GET /addons` liefert die genaue Liste, verlangt aber je nach Supervisor-Fassung eine höhere Rolle. Scheitert das, reicht `GET /addons/self/info` — das darf die Default-Rolle immer, und aus dem eigenen Hostnamen lässt sich der Präfix für die Geschwister-Add-ons ableiten. Dem Portal `hassio_role: manager` zu geben (dürfte dann Add-ons starten, stoppen, installieren) war der Auskunft nicht wert
- Damit funktioniert das Portal auch dann noch, wenn ein Messenger-Add-on seinen Port nicht mehr im LAN veröffentlicht. Das ist die Voraussetzung dafür, die ungeschützten Direktports abschalten zu können
- nginx löst den Namen erst beim Request auf (Variable in `proxy_pass` plus `resolver` aus `/etc/resolv.conf`). Mit einem festen Namen hätte nginx den Start verweigert, solange ein Add-on aus ist — und alle Messenger stehen auf `boot: manual`. Ein gestopptes Add-on landet weiterhin auf der gewohnten „nicht erreichbar“-Seite
- Die Option `internal_host` behält Vorrang: wer sie gesetzt hat, merkt keinen Unterschied. Ohne Supervisor-Antwort fällt das Portal auf den bisherigen Weg über den HA-Host zurück
- Der Gateway-Aufruf (`ip route`) wird gemerkt statt bei jeder Statusabfrage neu ausgeführt

## [1.2.19] - 2026-08-28
- Die Ampel auf der Kachel sagt jetzt mehr als „Port offen": das Portal liest den Selbsttest des jeweiligen Add-ons mit (`/api/selfcheck`) und zeigt einen **eigenen Zustand**, wenn die Verbindung zwar steht, der Anbieter aber etwas umgebaut hat — „Online – mit Einschränkung", bernsteinfarbener Punkt mit Ring
- Der Mauszeiger auf der Ampel verrät die Einzelheiten: bei Grün „Verbunden – Selbsttest ohne Befund (16 Bausteine, 4 Antwortformen geprüft)", bei Bernstein die betroffenen Funktionen
- Die Kachel bleibt in diesem Zustand **anklickbar** — anders als bei „nicht erreichbar" läuft der Messenger ja weiter
- Add-ons ohne diese Route (Telegram, Signal) verhalten sich unverändert: keine Aussage ist kein Fehler
- Ergebnisse werden 5 Minuten gemerkt, ein „kennt die Route nicht" 30 Minuten — die Statusabfrage läuft im Sekundentakt, der Selbsttest dahinter nur alle paar Stunden

## [1.2.18] - 2026-08-28
- Feature: **Filter in der Konsole.** Vier Schalter fuer ERROR, WARN, INFO und DEBUG blenden Ebenen aus, ein Textfeld filtert zusaetzlich nach Inhalt, der Zaehler rechts zeigt „sichtbar/gesamt". Ein Filterwechsel wirkt auch auf bereits eingetroffene Zeilen, weil die letzten 1500 Meldungen im Browser vorgehalten werden. Die Auswahl bleibt ueber einen Seitenwechsel hinweg erhalten
- Pythons `CRITICAL` laeuft dabei unter ERROR, `WARNING` unter WARN. Zeitstempel hatten die Zeilen hier schon — anders als bei WhatsApp, Telegram und Signal war nur der Filter nachzuruesten
- Gleiche Funktion wie im WhatsApp-Add-on ab 1.8.0

## [1.2.17] - 2026-08-28
- Fix: Die rote „Neu"-Markierung war rein gerätebasiert (`localStorage`) — eine am Handy gelesene Nachricht blieb am Desktop weiter als neu markiert. Der Gelesen-Stand liegt jetzt serverseitig in `/data/read_state.json` und wird von allen Geräten geteilt; beim Öffnen einer Kachel meldet der Browser ihn per `sendBeacon` an die neue Route `POST /api/mark-read`

## [1.2.16] - 2026-08-25
- Fix: WhatsApps Zwischenzustand `authenticated` (QR gescannt, Chats werden noch geladen) zählt nicht mehr als „Online" — in dieser Phase lehnt das Add-on Sendeversuche mit HTTP 503 ab. Als echte Verbindung gelten nur noch `connected`, `linked` und `ready`
- Der Tooltip bei „Verbindungsproblem" nennt jetzt auch den rohen Add-on-Status (z. B. `waiting_for_scan`, `not-linked`, `disconnected`), wenn das Add-on keinen Fehlertext liefert

## [1.2.15] - 2026-08-25
- Fix: **„Online" war irreführend.** Der Status kam bisher allein daher, dass der TCP-Port des Add-ons erreichbar war — ein Add-on, dessen Weboberfläche läuft, dessen Messenger-Verbindung aber abgerissen ist (z. B. Telegram nach `ENETUNREACH`), wurde trotzdem grün als „Online" angezeigt. Das Portal fragt jetzt zusätzlich `/api/status` des jeweiligen Add-ons ab und wertet nur `connected`, `linked`, `ready` oder `authenticated` als echte Verbindung
- Neu: Dritter Status **„Verbindungsproblem"** (oranger Punkt) für Add-ons, die erreichbar, aber nicht verbunden sind. Der Tooltip nennt den Grund aus dem Add-on. Die Kachel bleibt anklickbar, damit man die Oberfläche zum Neuverbinden öffnen kann — nur wirklich unerreichbare Add-ons werden weiterhin gesperrt
- Add-ons ohne `/api/status`-Route gelten wie bisher als online, sobald ihr Port erreichbar ist

## [1.2.14] - 2026-07-31
- map: `addon_config` → `app_config` (Home-Assistant-Supervisor hat `addon_config` seit 2026.07 als Legacy-Name markiert, neuer Name ist `app_config`).

## [1.2.13] - 2026-07-28

### Added
- Tastatur-Shortcut **Alt+Shift+H** springt in allen proxierten Add-ons zurück zum Portal, als Fallback falls der schwebende Button mal nicht sichtbar ist (z. B. wegen Browser-Cache/Service-Worker)

## [1.2.12] - 2026-07-27

### Fixed
- Schwebender „Zurück zum Portal"-Button wurde in proxierten Add-ons nicht mehr angezeigt: `sub_filter_types` in `gen_nginx.py` wurde explizit auf `text/javascript application/javascript application/json` gesetzt, das überschreibt nginx' Default (`text/html`) komplett statt ihn zu erweitern — dadurch griff die `</body>`-Injection des Buttons nie mehr auf echten HTML-Seiten. `text/html` wieder in `sub_filter_types` aufgenommen

## [1.2.11] - 2026-07-25

### Fixed
- Medien-Upload (z. B. Bild aus Zwischenablage einfügen) an proxierte Add-ons wie WhatsApp scheiterte mit `502 Bad Gateway`, sobald die Datei über 1 MB lag — `gen_nginx.py` setzte nirgends `client_max_body_size`, damit griff der nginx-Alpine-Default von 1 MB, obwohl das WhatsApp-Add-on selbst (`multer`) 64 MB erlaubt. `client_max_body_size 64m;` jetzt global im generierten Server-Block gesetzt

## [1.2.10] - 2026-07-09

### Fixed
- Add-on beendete sich bei jedem Stop/Update mit Exit-Code 137 (SIGKILL statt sauberem Stop): `run.sh` macht den Flask-Prozess per `exec` zu PID 1, ohne eigenes Init-System ignoriert der Kernel bei PID 1 unbehandelte Signale wie SIGTERM (Linux-Sonderfall), der Supervisor musste nach Timeout hart killen. `init: false` → `init: true` in `config.yaml` (HA Supervisor stellt jetzt ein Mini-Init als echte PID 1) plus eigener `SIGTERM`-Handler in `app.py` (`os._exit(0)` — keine Hintergrund-Threads, Sessions werden bereits synchron gespeichert, kein Cleanup nötig) sorgen jetzt für einen sauberen Exit-Code 0.

## [1.2.9] - 2026-07-07

### Fixed
- Abgelaufene Session wurde nicht erkannt: `/status`-Polling ignorierte 401-Antworten stillschweigend, Portal blieb mit eingefrorenen Status-Punkten offen statt zum Login weiterzuleiten. Jetzt Redirect zu `/login` bei 401

## [1.2.8] - 2026-06-10

### Added
- HA Ingress-Unterstützung: Add-on jetzt direkt in der HA-Seitenleiste erreichbar (`ingress: true`, Port 17770, Icon `mdi:message-badge`)
- `_IngressMiddleware`: liest `X-Ingress-Path` Header, setzt `SCRIPT_NAME` – alle `url_for()`-Links passen sich automatisch an den Ingress-Pfad an
- Auth-Bypass für Ingress: HA übernimmt die Authentifizierung; Login-Seite und Logout-Button werden via Ingress nicht angezeigt

### Fixed
- Header-Logo: `href="/"` → `url_for('index')` (absolutes `/` funktionierte nicht via Ingress)
- Console `/api/logs`-URL: hardcoded absoluter Pfad durch `url_for('api_logs')` ersetzt
- `proxy_cookie_path` in nginx entfernt: scoped Cookies funktionierten mit Ingress-URLs nicht (cookies sind nun unscoped)

### Changed
- `X-Ingress-Path` Header wird jetzt in allen nginx `proxy_pass`-Blöcken an Flask weitergeleitet

## [1.2.7] - 2026-06-09

### Added
- `webui`-Feld in config.yaml: HA zeigt jetzt den Button „Benutzeroberfläche öffnen" — passt sich automatisch an den konfigurierten Host-Port an

## [1.2.6] - 2026-06-09

### Fixed
- `mobile-web-app-capable` Meta-Tag ergänzt (Deprecation-Warnung im Browser behoben)

## [1.2.5.1] - 2026-06-08

### Dependencies
- Dependabot: Abhaengigkeiten aktualisiert

## [1.2.5] - 2026-06-08

### Security
- Open Redirect: `request.referrer` in `set_lang()` via `urlparse` validiert — nur relative Pfade erlaubt (CodeQL MEDIUM #129)

## [1.2.4] - 2026-06-08

### Security
- Cookie Injection: `cookie_lang` aus Literal statt URL-Parameter in `set_lang()` (CodeQL MEDIUM #47)

## [1.2.3] - 2026-06-07

### Security
- Flask 3.0.3 → 3.1.3 (Dependabot-Alert behoben)

---

## [1.2.2] - 2026-06-07
### Added
- Disconnect-Erkennung: `visibilitychange` (Tab/Laptop-Aufklappen), `online`/`offline`-Events, `navigator.onLine`-Check beim Start
- Offline-Banner: abdunkelndes Overlay mit animiertem 📡, lokalisierten Texten (DE/EN) und „Neu laden"-Button

## [1.2.1] - 2026-06-06
### Fixed
- PWA-Icon: icon-192.png und icon-512.png in static/-Ordner kopiert, damit das Manifest die Icons korrekt laden kann

## [1.2.0] - 2026-06-06
### Added
- Nachrichtentyp-Icons in der Übersicht: 💬 Text, 🖼️ Foto, 📄 Dokument, 🎙️ Sprachnachricht, 📹 Video, 📍 Standort
- Offline-Messenger: Karte ausgegraut, Hover deaktiviert, Klick blockiert
- Status wird sofort aktualisiert wenn der Tab wieder in den Vordergrund kommt (visibilitychange)
- In-App Console: Doppelklick auf „MessengerPortal" öffnet draggbares Floating-Window mit Backend-Logs
### Improved
- Browser-Benachrichtigungen robuster: Timing-Tracking per Timestamp, Benachrichtigung auch bei zweiter Nachricht im selben Messenger

## [1.1.15] - 2026-06-06
- Fix: DEBUG-Logs in Console sichtbar — Root-StreamHandler auf INFO, Root-Logger auf DEBUG; DEBUG bleibt aus HA-Log heraus

## [1.1.14] - 2026-06-06
- Fix: Console-Zustand (offen/geschlossen) wird in localStorage gespeichert und beim Laden der Seite wiederhergestellt — Console bleibt offen wenn zu einem Messenger navigiert und zurückgekehrt wird

## [1.1.13] - 2026-06-06
- Fix: Console-Fenster immer noch sofort weg — dblclick feuert erst nach zwei click-Events die bereits navigieren; onclick auf Span blockiert jetzt ebenfalls die Navigation

## [1.1.12] - 2026-06-06
- Fix: Console-Fenster erschien kurz und verschwand sofort — Doppelklick auf Span innerhalb <a href="/"> löste Seitennavigation aus; event.preventDefault() + stopPropagation() hinzugefügt

## [1.1.11] - 2026-06-06
- Fix: Jinja2 TemplateSyntaxError — @media(){#...} wurde als Kommentar-Anfang interpretiert; Leerzeichen nach { eingefügt

## [1.1.10] - 2026-06-06
- Neu: In-App Console (Doppelklick auf "MessengerPortal") — draggbares Floating-Window; Python logging.Handler schreibt in Deque-Buffer (300 Einträge); GET /api/logs?since= Flask-Route; stille DEBUG-Logs beim Messenger-Status-Poll

## [1.1.9] - 2026-06-06
- Fix: TYPE_ICONS ergänzt um video (📹) und location (📍) — wurden bisher ohne Icon angezeigt

## [1.1.8] - 2026-06-05
- feat: Nachrichtentyp-Icon in Übersicht (💬 text, 🖼️ photo, 📄 document, 🎙️ voice)

## [1.1.7] - 2026-06-04
- fix: Log-Zeitstempel vollständig in allen Ausgaben (force=True / UVICORN_LOG_CONFIG)

## [1.1.6] - 2026-06-04
- Log-Ausgaben mit Datum und Uhrzeit: `[INFO] [YYYY-MM-DD HH:MM:SS] Nachricht`

## [1.1.5] – 2026-05-31

### Added
- Offline-Messenger: Karte ausgegraut, Hover deaktiviert, Klick blockiert

## [1.1.4] – 2026-05-31

### Added
- Status wird sofort aktualisiert wenn die Seite wieder in den Vordergrund kommt (visibilitychange)

## [1.1.3] – 2026-05-30

### Fixed
- Benachrichtigungsverzögerung: PAGE_LOAD_TIME tracken – beim ersten Poll wird
  sofort benachrichtigt wenn die Nachricht nach dem Seitenaufruf ankam, statt
  erst beim zweiten Poll (ein voller poll_interval später)

## [1.1.2] – 2026-05-30

### Fixed
- Benachrichtigungslogik: Tracking per Timestamp statt Zustandswechsel – Benachrichtigung kommt jetzt auch bei zweiter Nachricht im selben Messenger und nach Seitenneuladen

## [1.1.1] – 2026-05-30

### Fixed
- Version-Bump damit HA das Update erkennt

## [1.1.0] – 2026-05-30

### Added
- Browser-Benachrichtigungen: Glocken-Icon im Header zum Aktivieren/Deaktivieren
- Stummschaltung für 1 Stunde, 4 Stunden oder bis morgen 08:00 Uhr
- Benachrichtigung erscheint nur wenn eine neue Nachricht *während der Sitzung* eintrifft (kein Spam beim ersten Laden)
- Glocken-Icon zeigt Zustand: aktiv (blau), stummgeschaltet (gelber Punkt), inaktiv (grau)

## [1.0.9] – 2026-05-30

### Changed
- „Letzte Nachricht": Datum/Uhrzeit und Absender stehen jetzt auf separaten Zeilen

## [1.0.8] – 2026-05-30

### Removed
- Ingress-Support entfernt (zu komplex für den Nutzen)

## [1.0.7] – 2026-05-30

### Fixed
- Status-API: JS nutzt jetzt Jinja2 `url_for('status')` statt hardcoded `/status` → funktioniert via Ingress
- Messenger-Karten: Link-Prefix kommt aus `request.script_root` → korrekte Ingress-URL für Proxy-Routen
- Zurück-Button: navigiert zu `../../` (relativ) statt `/` → funktioniert für Direkt- und Ingress-Zugriff

## [1.0.6] – 2026-05-30

### Fixed
- Ingress 404: HA Ingress folgt Redirects intern ohne X-Ingress-Path → Login-Redirect schlug fehl
- Lösung: Requests via Ingress gelten als authentifiziert (HA übernimmt die Authentifizierung)
- nginx `auth_request` leitet X-Ingress-Path weiter damit auch Proxy-Routen via Ingress funktionieren

## [1.0.5] – 2026-05-30

### Fixed
- Ingress 404: PATH_INFO wird jetzt manuell bereinigt – HA strippt den Ingress-Prefix nicht immer selbst
- `panel_title: MessengerPortal` ergänzt

## [1.0.4] – 2026-05-30

### Added
- HA Ingress-Unterstützung: Add-on ist jetzt direkt in der HA-Oberfläche erreichbar (`ingress: true`, Port 17770, Icon `mdi:message-badge`)
- X-Ingress-Path Header wird ausgewertet – alle Flask-URLs (Redirects, Links, Formulare) passen sich automatisch an den Ingress-Pfad an

### Fixed
- Sonnen-Icon (Light Mode): korrektes Material Design SVG mit sichtbarem Kreis (Radius 5px statt 3px) und geraden Strahlen

## [1.0.3] – 2026-05-30

### Fixed
- Datumsanzeige „Heute/Gestern" basiert jetzt auf Kalendertagen statt 24h-Differenz – Nachrichten vom Vortag werden korrekt als „Gestern" angezeigt

## [1.0.2] – 2026-05-30

### Changed
- „Zurück zum Portal"-Button wird auf mobilen Geräten (≤ 600px) ausgeblendet

## [1.0.1] – 2026-05-29

### Fixed
- IP-Erkennung: `CF-Connecting-IP` Header wird bevorzugt (echte öffentliche IP bei Cloudflare Tunnel)
- Rate-Limiter sperrt nun korrekt pro echte Client-IP statt immer die Docker-Gateway-IP

## [1.0.0] – 2026-05-29
- Erste stabile Produktivversion

## [0.0.24] – 2026-05-29

### Fixed
- Signal-Icon: Ring-Logo durch korrektes Speech-Bubble-App-Icon ersetzt

## [0.0.23] – 2026-05-29

### Fixed
- „Letzte Nachricht"-Text bricht jetzt um statt abgeschnitten zu werden
- „Öffnen"-Button erstreckt sich über die volle Kartenbreite und ist zentriert

## [0.0.22] – 2026-05-29

### Added
- Neue Config-Option `poll_interval` (Sekunden, Standard 30, Minimum 5): steuert wie oft Status und letzte Nachricht abgefragt werden

## [0.0.21] – 2026-05-29

### Added
- Neue Nachricht: Karte leuchtet mit pulsierendem Farbrand + rotem Badge auf dem Icon wenn eine neue Nachricht seit dem letzten Öffnen angekommen ist
- Glow verschwindet beim Klick auf den Messenger (localStorage speichert Öffnungszeitpunkt)

## [0.0.20] – 2026-05-29

### Added
- Absender der letzten Nachricht wird neben dem Zeitpunkt angezeigt (z.B. „Letzte Nachricht: Heute 07:24 · Max Mustermann")

## [0.0.19] – 2026-05-29

### Fixed
- Doppelte Zeitanzeige entfernt: localStorage "Zuletzt geöffnet" war redundant zur API "Letzte Nachricht" und wurde entfernt

## [0.0.18] – 2026-05-29

### Added
- Zeitpunkt der letzten Nachricht je Messenger auf der Karte angezeigt (via `/api/last-received`)
- Alle drei Messenger-APIs werden parallel abgefragt (ThreadPoolExecutor) – kein sequentielles Warten

## [0.0.17] – 2026-05-29

### Fixed
- PWA über Cloudflare Tunnel: `crossorigin="use-credentials"` auf manifest-Link – Browser sendet jetzt Session-Cookie beim Manifest-Request, Cloudflare leitet nicht mehr zur Login-Seite um
### Changed
- Portal-Button ist jetzt frei verschiebbar (Drag & Drop, Maus + Touch); Position wird in localStorage gespeichert

## [0.0.16] – 2026-05-29

### Fixed
- nginx: `proxy_pass` mit URI-Pfad in named location (`@offline_*`) ist nicht erlaubt – auf `rewrite ^ /proxy-offline break` + `proxy_pass` ohne Pfad umgestellt

## [0.0.15] – 2026-05-29

### Fixed
- PWA über Cloudflare Tunnel: sw.js und manifest.json erhalten jetzt vollständige No-Cache-Header (`no-cache, no-store, must-revalidate` + `Pragma: no-cache` + `Expires: 0`) damit Cloudflare sie nicht cached
- `Service-Worker-Allowed: /` Header auf sw.js für korrekten Scope

## [0.0.14] – 2026-05-29

### Added
- Floating „Zurück zum Portal"-Button wird in jeden proxied Messenger injiziert
- Eigene 502-Fehlerseite wenn ein Messenger offline ist (statt nginx-Rohfehler)
- Sessions werden auf Disk gespeichert – bleiben nach Add-on-Neustart erhalten
- Favicon-Route `/favicon.ico` für das Portal-Icon im Browser-Tab
- „Zuletzt geöffnet"-Anzeige auf jeder Messenger-Karte (per localStorage)
### Fixed
- Health- und Status-Endpoints erzeugen keine Log-Einträge mehr (nginx + werkzeug)
- `Accept-Encoding: ""` beim Proxy-Pass damit sub_filter auch bei gzip funktioniert

## [0.0.13] – 2026-05-29

### Fixed
- Login-Fehlermeldung wurde nach falschem Passwort nicht mehr angezeigt (Regression aus 0.0.12)

## [0.0.12] – 2026-05-29

### Fixed
- nginx: `text/html` aus `sub_filter_types` entfernt – war bereits Standard, verursachte Duplicate-MIME-Warnungen im Log
### Added
- Login-Logging: erfolgreiche Logins als INFO, fehlgeschlagene als WARNING im Add-on-Log

## [0.0.11] – 2026-05-29

### Fixed
- PWA-Installation: manifest.json und sw.js werden jetzt von `/` serviert statt `/static/` – Service Worker hat damit korrekten Scope und Browser zeigt Install-Symbol

## [0.0.10] – 2026-05-29

### Added
- Status-Anzeige auf jeder Messenger-Karte: grüner Punkt (Online) / roter Punkt (Offline)
- `/status`-Endpoint prüft per TCP-Socket ob der konfigurierte Port erreichbar ist
- Automatisches Polling alle 30 Sekunden

## [0.0.9] – 2026-05-29

### Changed
- Messenger öffnen sich im gleichen Fenster statt in einem neuen Tab

## [0.0.8] – 2026-05-29

### Changed
- `internal_host` wird jetzt automatisch über `ip route` erkannt – kein manuelles Eintragen nötig
- Manueller Override über die Option `internal_host` weiterhin möglich

## [0.0.7] – 2026-05-29

### Changed
- Architektur auf nginx Reverse Proxy umgestellt: Flask läuft intern auf Port 5000, nginx lauscht auf 17770
- Messenger-Buttons öffnen `/proxy/<icon>/` statt direktem Port – Messenger-Ports müssen von außen nicht erreichbar sein
- nginx prüft Session via `auth_request` vor dem Proxying (WebSocket-Support inklusive)
- Neue Option `internal_host` (Standard: `172.30.32.2`): interne IP des HA-Hosts

## [0.0.6] – 2026-05-29

### Changed
- Dockerfile: unnötiges `sed` entfernt (`.gitattributes` erzwingt bereits LF für `.sh`)
- run.sh: `python3` → `python` zur Konsistenz mit CardBoard

## [0.0.5] – 2026-05-29

### Fixed
- run.sh: Shebang auf `#!/bin/sh` geändert (Alpine hat kein bash), CRLF-Stripping im Dockerfile ergänzt

## [0.0.4] – 2026-05-29

### Fixed
- Dockerfile: HA-spezifisches Base-Image durch `python:3.11-alpine` ersetzt – behebt Multi-Arch-Build-Fehler im GitHub Actions Workflow

## [0.0.3] – 2026-05-29

### Added
- `image`-Feld in config.yaml: HA zieht das Image von GHCR statt lokal zu bauen

## [0.0.2] – 2026-05-29

### Added
- Brute-Force-Schutz: nach 5 Fehlversuchen wird die IP für 15 Minuten gesperrt (Log-Ausgabe)
- X-Forwarded-For-Unterstützung via ProxyFix – echte Client-IP wird auch hinter NGINX erkannt
- Fehlermeldung bei gesperrter IP (DE/EN)

## [0.0.1] – 2026-05-29

### Added
- Initiales Release
- Passwortgeschützte Login-Seite
- Zentrale Startseite mit Messenger-Karten (WhatsApp, Telegram, Signal)
- Konfigurierbare Session-Dauer
- Dark Mode / Light Mode mit automatischer Erkennung via `prefers-color-scheme`
- Manuelle Umschaltung und persistente Speicherung im Browser
- Mehrsprachige UI: Deutsch und Englisch, automatische Spracherkennung via `Accept-Language`
- Responsive Design / Mobile-optimiert
- PWA-Unterstützung (Manifest + Service Worker)
- Konfigurierbare Messenger: Name, Icon, Port, aktiviert/deaktiviert
