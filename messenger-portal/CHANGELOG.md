# Changelog – MessengerPortal

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
