# GitPulse

**GitHub Control Panel für Home Assistant**

GitHub-Übersicht direkt im HA-Dashboard: Pull Requests, Issues, CI-Läufe, Security-Alerts, Releases und eigene Aktivitäten — alles auf einen Blick. Unterstützt Telegram-, E-Mail- und Browser-Benachrichtigungen, GitHub-Webhooks für Echtzeit-Updates und lässt sich als PWA installieren.

## Funktionen

- **Repos** — Übersicht aller Repos: offene PRs/Issues, letzter CI-Lauf, Stars/Forks/Watchers · Repo-Insights (Lizenz, CI, Security-Alerts)
- **Pull Requests** — Öffnen, mergen (merge / squash / rebase), kommentieren · Suche/Filter · Review-Status · Repo-Wechsler · aufklappbare Beschreibung (Markdown gerendert) · inline Kommentar-Vorschau
- **Issues** — Schließen, kommentieren · Suche/Filter · Repo-Wechsler · aufklappbare Beschreibung · inline Kommentar-Vorschau
- **CI / Actions** — Workflow-Läufe mit Schnellfiltern, Job+Step-Details, Dispatch, Stoppen, Neu starten, Löschen · **Workflow-Favoriten** · Repo-Wechsler
- **Releases** — Release-Tracker für beliebig viele Repos (eigene + beobachtete) inkl. HA Beta/RC · als gelesen markieren · **Releases anlegen**: Version in `custom_components/<domain>/manifest.json` bumpen, CHANGELOG-Eintrag schreiben und Release mit Tag erstellen (für Custom Integrations)
- **Security** — Dependabot · Code Scanning · Secret Scanning Alerts mit Schweregrad-Icons · **CodeQL Autofix**: Fix per Knopfdruck in neuen Branch committen
- **Meine Aktivität** — Alle eigenen offenen PRs und Issues + PRs mit Review-Anfrage · eigene Items schließen · neue-Kommentar-Benachrichtigungen
- **Branch Manager** — Branches auflisten, einzeln oder per Mehrfachauswahl löschen · Merge-Status (✓ gemergt / ↑N ungemergte Commits / offener PR) · geschützte Branches (main/dev/master/develop) · Cherry-Pick-Funktion
- **Add-on Manager** *(optional)* — Versionen bumpen, Changelog-Einträge schreiben und direkt aus der UI pushen
- **Console** — Internes Live-Log mit Auto-Scroll
- **Branch-Sync Kachel** — Zeigt pro Repo wie viele Commits dev vor/hinter main liegt (↑/↓) mit Farbkodierung
- **Benachrichtigungen** — Telegram · E-Mail (SMTP) · Browser-Benachrichtigungen — je Ereignistyp einzeln aktivierbar (inkl. Review-Anfragen und neuer Kommentare; selbst verfasste Kommentare lösen nichts aus)
- **Tages-Digest** — Optionale tägliche Zusammenfassung aller offenen PRs, Issues und Security-Alerts zu einer konfigurierbaren Uhrzeit (`digest_hour 0–23`)
- **Webhooks** — Optionaler Echtzeit-GitHub-Empfänger (< 1 s statt bis zu 5 Min. Polling)
- **PWA** — Installierbar, funktioniert hinter Cloudflare Tunnel und HA Cloud
- Dark / Light Mode · DE / EN · HA Ingress

## Schnellstart

1. GitHub Fine-Grained PAT erstellen → [DOCS.md](DOCS.md#github-token)
2. Token, Repos und optionale Funktionen in den Add-on-Einstellungen konfigurieren
3. Add-on starten

## Ports

| Port | Funktion |
|------|----------|
| `17792` | Web UI (direkt, ohne Ingress) |
| `17793` | GitHub-Webhook-Empfänger (optional — nur aktiv wenn `webhook_secret` gesetzt) |

## Dokumentation

Vollständige Konfigurationsreferenz, Token-Einrichtung, Telegram, E-Mail und Webhook-Konfiguration: **[DOCS.md](DOCS.md)**

---

# GitPulse

**GitHub Control Panel for Home Assistant**

Monitor pull requests, issues, CI runs, security alerts, releases and your own activity — all in one HA dashboard panel. Supports Telegram, e-mail and browser notifications, GitHub Webhooks for real-time updates, and installs as a PWA.

## Features

- **Repos** — Overview of all your repos: open PRs/issues, last CI run, stars/forks/watchers · repo insights badge (licence, CI, security alerts)
- **Pull Requests** — Open, merge (merge / squash / rebase), comment · search/filter · review status · repo switcher · expandable description (Markdown rendered) · inline comment preview
- **Issues** — Close, comment · search/filter · repo switcher · expandable description (Markdown rendered) · inline comment preview
- **CI / Actions** — Workflow runs with quick-filters, job+step details, dispatch, stop, re-run, delete · **Workflow Favorites** · repo switcher
- **Releases** — Release tracker for any number of repos (own + watched) incl. HA beta/RC · mark as read · **create releases**: bump the version in `custom_components/<domain>/manifest.json`, write a CHANGELOG entry and publish a tagged release (for custom integrations)
- **Security** — Dependabot · Code Scanning · Secret Scanning alerts with severity icons · **CodeQL Autofix**: commit a fix to a new branch with one click
- **My Activity** — All open PRs and issues you created + PRs where you are requested as reviewer · close own items · new-comment notifications · filter persistence across reloads
- **Branch Manager** — List branches, delete individually or in bulk · merge status (✓ merged / ↑N unmerged commits / open PR) · protected branches (main/dev/master/develop) · cherry-pick function
- **Add-on Manager** *(optional)* — Bump versions, write changelog entries and push directly from the UI
- **Console** — Live internal log with auto-scroll
- **Branch-Sync Tile** — Shows per repo how many commits dev is ahead/behind main (↑/↓) with colour coding
- **Notifications** — Telegram · e-mail (SMTP) · browser notifications — each type individually toggleable per event (incl. review requests)
- **Daily Digest** — Optional daily summary of all open PRs, issues and security alerts sent at a configurable hour (`digest_hour 0–23`)
- **Webhooks** — Optional real-time GitHub event receiver (< 1 s vs. up to 5 min polling)
- **PWA** — Installable, works behind Cloudflare Tunnel and HA Cloud
- Dark / Light mode · DE / EN · HA Ingress

## Quick Start

1. Create a GitHub Fine-Grained PAT → [DOCS.md](DOCS.md#github-token)
2. Configure token, repos and optional features in the add-on settings
3. Start the add-on

## Ports

| Port | Function |
|------|----------|
| `17792` | Web UI (direct, without Ingress) |
| `17793` | GitHub Webhook receiver (optional — only active when `webhook_secret` is set) |

## Documentation

Full configuration reference, token setup, Telegram, e-mail and webhook configuration: **[DOCS.md](DOCS.md)**
