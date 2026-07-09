# Changelog

## [1.0.15] - 2026-07-09

### Behoben
- Add-on beendete sich bei Stop/Update immer mit SIGKILL (exit 137) — der Python-Prozess läuft als PID 1 im Container ohne eigenen Init, der Kernel ignoriert SIGTERM daher stillschweigend. `init: true` gesetzt und ein eigener SIGTERM-Handler ergänzt, der einen laufenden Chromium-Kindprozess sauber stoppt und sich danach selbst mit exit 0 beendet

## [1.0.14] - 2026-06-04
- fix: Datum in Log-Zeitstempel ergänzt — war nur Uhrzeit, jetzt vollständig

## [1.0.13] - 2026-06-04
- Log-Ausgaben mit Datum und Uhrzeit: `[INFO] [YYYY-MM-DD HH:MM:SS] Nachricht`

## 1.0.12 - 2026-06-03
- Build: Image wird jetzt via GitHub Actions auf GHCR gebaut (ghcr.io/luckytriple7/playwright-browser)
- Build: Basis-Image auf debian:bookworm-slim, bashio durch jq ersetzt

## 1.0.11 - 2026-05-16

### Behoben
- Watchdog hat das Add-on neugestartet weil Loopback-Requests 503 bekamen — Loopback antwortet jetzt immer mit 200 (`{"status":"idle"}`) damit der Watchdog zufrieden ist, ohne Chromium zu starten

## 1.0.10 - 2026-05-16

### Behoben
- HA-Supervisor-Health-Check (`127.0.0.1 /json/version`) hat Chromium immer wieder neugestartet — HTTP-Requests von Loopback starten Chromium nicht mehr; externe Clients (Playwright) funktionieren weiterhin normal

## 1.0.9 - 2026-05-16

### Geändert
- Chromium-Startmeldung zeigt jetzt den Auslöser: `trigger: HTTP 172.30.33.13 /json/version` oder `trigger: WebSocket ...` — macht sichtbar warum Chromium (neu) startet

## 1.0.8 - 2026-05-16

### Behoben
- Idle-Timer lief nie ab — HTTP-Anfragen (z.B. Playwright-Health-Check `/json/version`) haben `_last_activity` immer wieder zurückgesetzt; nur noch WebSocket-Events und Chromium-Start setzen den Timer
- Log-Format vereinheitlicht: alle Meldungen folgen `[LEVEL] [HH:MM:SS] Nachricht`

## 1.0.7 - 2026-05-16

### Neu
- Verbindungs-Logging: Client-IP und Anzahl aktiver WebSocket-Verbindungen werden beim Verbinden und Trennen geloggt
- Chromium-Start durch HTTP-Request wird ebenfalls geloggt (z.B. wenn Playwright zuerst `/json/version` abfragt)

## 1.0.6 - 2026-05-16

### Geändert
- Lazy Start: Chromium startet erst beim ersten eingehenden CDP-Verbindungsversuch und wird nach Ablauf des Leerlauf-Timeouts automatisch beendet — 0% CPU wenn kein Client verbunden ist
- Neue Option `idle_timeout` (Standard: 5 Minuten) — Chromium stoppt wenn so lange keine aktive WebSocket-Verbindung besteht
- Weitere Chromium-Flags zum Reduzieren der Hintergrundaktivität: `--disable-extensions`, `--disable-gpu-compositing`, `--mute-audio`, `--no-pings`, `--disable-features=MediaRouter,TranslateUI`

## 1.0.5 - 2026-05-15

### Geändert

- `--headless=new` → `--headless` (alter Headless-Modus): der neue Modus startet einen vollständigen Renderer mit requestAnimationFrame-Loop (~60fps) was die konstanten ~4% CPU-Last im Leerlauf verursachte
- Unnötige Flags aus v1.0.4 wieder entfernt (`--jitless`, `--disable-v8-idle-tasks`, `--enable-low-end-device-mode`)

## 1.0.4 - 2026-05-15

### Geändert

- Chromium-Flags `--disable-v8-idle-tasks`, `--jitless` und `--enable-low-end-device-mode` hinzugefügt — reduziert CPU-Verbrauch im Leerlauf deutlich
- Healthcheck-Intervall von 30s auf 60s erhöht
- Monitor-Loop-Intervall von 5s auf 30s erhöht

## 1.0.3 - 2026-05-15

### Behoben

- `python3` zum Dockerfile hinzugefügt — war nicht im HA Basis-Image enthalten

## 1.0.2 - 2026-05-15

### Geändert

- nginx komplett durch einen Python-CDP-Proxy ersetzt (`cdp_proxy.py`)
- Der Python-Proxy schreibt `localhost:INTERNAL_PORT` → `container-hostname:CDP_PORT` direkt in der HTTP-Response um — zuverlässiger als nginx `sub_filter`
- WebSocket-Verbindungen (`/devtools/*`) werden transparent als Raw-Bytes weitergeleitet
- Keine nginx-Abhängigkeit mehr — funktioniert mit Standard-Python 3 aus dem HA-Basis-Image

## 1.0.1 - 2026-05-15

### Behoben

- `nginx` durch `nginx-full` ersetzt — Standard-`nginx`-Paket auf Debian enthält kein `sub_filter`-Modul, nginx startete dadurch nicht
- `sub_filter_types *` statt `sub_filter_types application/json` — Chromium gibt `application/json; charset=UTF-8` zurück, was vorher nicht gematcht hat
- WebSocket-Pfade (`/devtools/*`) in eigenen nginx-`location`-Block ohne `sub_filter` und ohne Buffering
- nginx-Konfigurationstest vor dem Start, damit Fehler sofort sichtbar sind
- Startup-Verifikation: prüft nach nginx-Start ob Port wirklich antwortet

## 1.0.0 - 2026-05-15

### Erstveröffentlichung

- Headless Chromium via `apt` auf Debian Bookworm (HA-Basis-Image)
- nginx-Proxy für CDP-Port mit Hostname-Rewriting für externe WebSocket-Verbindungen
- Unterstützung für amd64 und aarch64
- Automatische Erkennung durch den Claude Code Add-on über die Supervisor API
- Gesundheitsprüfung via CDP `/json/version` Endpoint
