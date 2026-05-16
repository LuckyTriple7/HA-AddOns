# Changelog

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
