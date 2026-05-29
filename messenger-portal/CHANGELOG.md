# Changelog – MessengerPortal

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
