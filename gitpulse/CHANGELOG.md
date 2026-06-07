# Changelog

## [0.0.3] - 2026-06-07

### Added
- HA Ingress Support: Add-on erscheint als Panel im HA-Seitenmenü (`mdi:github`, Titel "GitPulse")
- `_IngressMiddleware`: liest `X-Ingress-Path` Header und setzt WSGI `SCRIPT_NAME` korrekt
- manifest.json und sw.js werden jetzt dynamisch via Flask gerendert (Ingress-Prefix in `start_url`, `scope` und Service-Worker-Cache-Pfaden)
- Alle Frontend-URLs (fetch, EventSource, Links) nutzen den Ingress-Base-Pfad

---

## [0.0.2] - 2026-06-07

### Added
- PR mergen direkt aus dem Dashboard (Merge / Squash / Rebase Auswahl)
- Workflow manuell starten (Dispatch) mit Branch-Auswahl
- Fehlgeschlagene Workflow-Runs neu starten (Re-run)
- config.yaml: my_repos Beispiel-Eintrag entfernt (muss vom User befüllt werden)

### Changed
- PAT benötigt jetzt zusätzlich `write` auf Pull Requests und Actions

---

## [0.0.1] - 2026-06-07

### Added
- Initiales Release von GitPulse
- Dashboard mit 5 Tabs: Pull Requests, Issues, CI/Actions, Releases, Console
- GitHub Fine-Grained PAT Authentifizierung mit Token-Status und Ablauf-Warnung
- Eigene Repos: PRs, Issues, CI-Workflow-Runs
- Watch-Repos: Release-Tracking inkl. HA Beta/RC-Releases
- Bruteforce-Schutz (5 Fehlversuche → 15 Min Sperre)
- Browser-Benachrichtigungen für neue Releases (Web Notifications API)
- PWA-Support inkl. Cloudflare Tunnel Kompatibilität
- Offline-Banner bei Verbindungsabbruch
- Dark/Light Mode
- DE/EN Sprachunterstützung
- Telegram-Benachrichtigungen für neue Releases
- SSE (Server-Sent Events) für Live-Updates
- In-App Console mit HA-Log-Integration
- Automatisches Polling konfigurierbar (Standard: 300s)
