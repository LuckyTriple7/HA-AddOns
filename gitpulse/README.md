# GitPulse

**GitHub Control Panel for Home Assistant**

Monitor pull requests, issues, CI runs, security alerts, releases and your own activity — all in one HA dashboard panel. Supports Telegram, e-mail and browser notifications, GitHub Webhooks for real-time updates, and installs as a PWA.

## Features

- **Repos** — Overview of all your repos: open PRs/issues, last CI run, stars/forks/watchers · repo insights badge (licence, CI, security alerts)
- **Pull Requests** — Open, merge (merge / squash / rebase), comment · search/filter · review status · repo switcher · expandable description (Markdown rendered) · inline comment preview
- **Issues** — Close, comment · search/filter · repo switcher · expandable description (Markdown rendered) · inline comment preview
- **CI / Actions** — Workflow runs with quick-filters, job+step details, dispatch, stop, re-run, delete · **Workflow Favorites** · repo switcher
- **Releases** — Release tracker for any number of repos (own + watched) incl. HA beta/RC · mark as read
- **Security** — Dependabot · Code Scanning · Secret Scanning alerts with severity icons · repo switcher
- **My Activity** — All open PRs and issues you created + PRs where you are requested as reviewer · close own items · new-comment notifications · filter persistence across reloads
- **Add-on Manager** *(optional)* — Bump versions, write changelog entries and push directly from the UI
- **Console** — Live internal log with auto-scroll
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
