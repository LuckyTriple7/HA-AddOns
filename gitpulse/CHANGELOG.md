# Changelog

## [0.0.10] - 2026-06-07

### Fixed
- Repos ohne Releases (HTTP 404 auf `/releases/latest`) werden beim ersten Poll erkannt und danach bis zum Add-on-Neustart aus der Abfrage ausgeschlossen — kein Spam mehr im Log

---

## [0.0.9] - 2026-06-07

### Changed
- Stat-Kacheln (Repos, PRs, Issues, Releases) aus dem Pull-Requests-Tab herausgezogen und dauerhaft oberhalb der Tab-Leiste platziert — immer sichtbar, unabhängig vom aktiven Tab

---

## [0.0.8] - 2026-06-07

### Fixed
- Externe Links öffnen korrekt in neuem Fenster in HA PWA: programmatischen window.open()-Aufruf entfernt, stattdessen echtes `<a target="_blank">` — nur echter User-Click löst in PWA neues Fenster aus, kein Popup-Blocker-Problem

---

## [0.0.7] - 2026-06-07

### Added
- Auto-Refresh nach Aktionen (Merge, Dispatch, Re-run): 5s Countdown im Header, dann automatischer Poll
- Countdown-Badge blinkt im Header während des Wartens

---

## [0.0.6] - 2026-06-07

### Changed
- Kein Login erforderlich hinter HA Ingress — HA übernimmt die Authentifizierung
- Direkter Port-Zugang (17792) erfordert weiterhin Login

---

## [0.0.5] - 2026-06-07

### Fixed
- Externe Links öffnen hinter HA Ingress korrekt in neuem Fenster: Link wird im Parent-Frame (HA-Frontend) erzeugt und geklickt, umgeht Iframe-Sandbox zuverlässig

---

## [0.0.4] - 2026-06-07

### Fixed
- Externe GitHub-Links (PRs, Issues, CI-Runs, Releases) öffnen hinter HA Ingress korrekt in einem neuen Browserfenster via `window.open()` statt `target="_blank"` (Iframe-Limitierung)

---

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
