# Changelog

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
