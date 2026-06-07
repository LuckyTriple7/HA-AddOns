# GitPulse

**GitHub Control Panel für Home Assistant**

Zeigt Pull Requests, Issues, CI-Status, Releases und Repo-Statistiken auf einen Blick — direkt im HA-Dashboard. Unterstützt Telegram-Benachrichtigungen und GitHub Webhooks für Echtzeit-Updates.

## Features

- **Repos-Tab** — Übersicht aller eigenen Repos mit PRs, Issues, CI-Status, Stars/Forks/Watchers
- **Pull Requests** — Öffnen, mergen (Merge/Squash/Rebase), kommentieren · Suche/Filter · Review-Status
- **Issues** — Schließen, kommentieren · Suche/Filter
- **CI / Actions** — Workflow-Runs mit Quickfiltern, Jobs+Steps, Dispatch, Stopp, Wiederholen, Löschen · **Workflow-Favoriten**
- **Releases** — Release-Tracker für beliebige Repos inkl. HA Beta/RC · als gelesen markieren
- **Console** — Internes Live-Log
- **Telegram** — Benachrichtigungen für PRs, Issues, Workflow-Start/-Ende, Releases, Stars/Forks-Änderungen
- **Webhooks** — Optionaler Echtzeit-Empfang von GitHub-Events (< 1 s statt bis zu 5 Min. Polling)
- **PWA** — Installierbar, funktioniert hinter Cloudflare Tunnel und HA Cloud
- Dark / Light Mode · DE / EN · HA Ingress

## Schnellstart

1. GitHub Fine-Grained PAT erstellen → [DOCS.md](DOCS.md#github-token)
2. Token, Repos und optionale Features in den Add-on-Einstellungen konfigurieren
3. Add-on starten

## Ports

| Port | Funktion |
|------|----------|
| `17792` | Web-UI (direkt, ohne Ingress) |
| `17793` | GitHub Webhook-Empfang (optional, nur aktiv wenn `webhook_secret` gesetzt) |

## Dokumentation

Vollständige Konfigurationsreferenz, Token-Setup, Telegram- und Webhook-Einrichtung: **[DOCS.md](DOCS.md)**
