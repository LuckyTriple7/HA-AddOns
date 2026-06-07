# Changelog

## [0.1.11] - 2026-06-07

### Fixed
- Dispatch Branch-Dropdown: `/api/branches` gab 500 zurück — `_gh_get_paginated` wurde mit ungültigem `params=`-Keyword aufgerufen (per_page ist bereits intern hardcodiert)

---

## [0.1.10] - 2026-06-07

### Fixed
- Token-Badge Mouseover: `token_expires_on` und `token_days` fehlten im JS-Übersetzungsobjekt `T` → "undefined" im Tooltip

---

## [0.1.9] - 2026-06-07

### Changed
- API Rate-Limit-Anzeige im Header: styled Badge wie Token-Badge — grün (>500), gelb (<500), rot (<200); Mouseover zeigt verbleibende Prozent und Reset-Zeit

---

## [0.1.8] - 2026-06-07

### Added
- Telegram: Benachrichtigung wenn ein Workflow **gestartet** wird (▶️) — mit Workflow-Name, Branch, Trigger-Typ, Autor und Commit-SHA
- Telegram: Benachrichtigung wenn ein Workflow **beendet** wird (✅/❌/⏹/⏭/⏱) — mit Abschlussstatus in Klartext

### Fixed
- CI-Tracking: neuer Run wurde bisher nicht von "noch laufendem Run ohne Conclusion" unterschieden (`_known_run_conclusions` nutzt jetzt explizite `in`-Prüfung statt `.get()`)

---

## [0.1.7] - 2026-06-07

### Changed
- Dispatch-Modal: Branch/Tag-Feld ist jetzt ein Dropdown — Branches werden on-demand per `/api/branches` von GitHub geladen, Default-Branch ist vorausgewählt

### Added
- Backend: neue Route `GET /api/branches?repo=owner/repo` liefert alle Branches des Repos

---

## [0.1.6] - 2026-06-07

### Changed
- Token-Badge im Header: Mouseover zeigt Ablaufdatum + verbleibende Tage
- Token-Badge wird rot wenn der Token in weniger als 14 Tagen abläuft (statt nur grün)

---

## [0.1.5] - 2026-06-07

### Added
- HA Add-on Konfigurationsübersetzungen: `translations/de.yaml` und `translations/en.yaml` — alle Config-Optionen haben jetzt Namen und Beschreibungen in der HA UI (wie bei SysWatch)

---

## [0.1.4] - 2026-06-07

### Fixed
- Kritischer JS-Fehler in `renderSummary`: `newRel` war undefiniert → Exception brach `render()` ab, wodurch alle Tabs (PRs, Issues, CI, Releases), Token-Badge und Rate-Limit-Anzeige leer blieben

---

## [0.1.3] - 2026-06-07

### Changed
- "Jetzt abfragen"-Button im Header: Text entfernt, nur noch Icon (Tooltip bleibt via `title`)
- DE/EN-Sprachbuttons werden auf Mobilgeräten (≤600 px) ausgeblendet — Browsersprache wird bereits automatisch erkannt

---

## [0.1.2] - 2026-06-07

### Added
- Stat-Kacheln sind jetzt klickbar — direkter Sprung in den zugehörigen Tab (PRs → Pull Requests, Issues → Issues, Workflows → CI, Releases → Releases)
- Neue Kachel "Workflows": zeigt Gesamtzahl der Runs; grün = alles OK, gelb = läuft, rot = Fehler vorhanden

---

## [0.1.1] - 2026-06-07

### Added
- **Repo-Verwaltung in GitPulse** (⚙-Button im Header): Repos direkt in der UI hinzufügen/entfernen, gespeichert in `/data/gitpulse_repos.json` — überlebt Add-on-Updates dauerhaft; HA-Options.json wird für Repos ignoriert sobald die UI-Config existiert
- **Telegram Startup-Nachricht**: beim ersten Poll nach Add-on-Start wird eine Zusammenfassung (offene PRs + Issues pro Repo) per Telegram geschickt
- Quelle der Repo-Config im Settings-Modal sichtbar (grün = GitPulse-managed, gelb = HA-Options)

### Fixed
- Repos gehen nach Add-on-Updates nicht mehr verloren

---

## [0.1.0] - 2026-06-07

### Added
- **Rate-Limit-Badge** im Header: zeigt verbleibende GitHub API-Aufrufe + Zeit bis Reset; färbt sich gelb/rot bei Engpass
- **PR Review-Status**: ✓ Approved / ✗ Changes requested / ○ Pending direkt in der PR-Zeile; Kommentaranzahl (PR + Review-Kommentare)
- **Telegram-Benachrichtigungen** für neue PRs, neue Issues und CI-Failures (zusätzlich zu Releases)
- **Issues schließen** direkt aus dem Dashboard (✕-Button)
- **Issues kommentieren** direkt aus dem Dashboard (💬-Button + Modal)
- **ETag-Support** in der GitHub API: bedingte Anfragen mit `If-None-Match` — 304-Antworten verbrauchen kein Rate-Limit
- **Automatische Poll-Intervall-Anpassung**: bei <500 verbleibenden Calls wird der Intervall verdoppelt, bei <100 verdreifacht, bei Erschöpfung wird bis zum Reset gewartet

---

## [0.0.14] - 2026-06-07

### Added
- CI/Actions: Workflow-Runs zeigen jetzt Trigger-Typ (Push/PR/Manuell/…), Commit-SHA + Message, Autor-Avatar und Laufzeit
- CI/Actions: Klick auf ▾ klappt Jobs + Steps mit Einzellaufzeiten auf (on-demand, kein Extra-Poll)
- Backend: neue Route `/api/ci/jobs` liefert Jobs + Steps eines Runs

---

## [0.0.13] - 2026-06-07

### Fixed
- Dispatch-Modal: Branch/Tag-Feld wird automatisch mit dem Default-Branch des Repos vorausgefüllt (statt hardcodiertem "main")

---

## [0.0.12] - 2026-06-07

### Changed
- Abmelden-Button im Header: Text entfernt, nur noch Icon (Tooltip bleibt erhalten)

---

## [0.0.11] - 2026-06-07

### Added
- Laufende Workflow-Runs können direkt aus dem CI-Tab abgebrochen werden (■ Stopp-Button bei Status `in_progress`, `queued`, `waiting`)

---

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
