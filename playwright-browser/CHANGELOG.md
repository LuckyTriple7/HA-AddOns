# Changelog

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
