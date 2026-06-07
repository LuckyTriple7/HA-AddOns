# GitPulse — Dokumentation

## GitHub Token

GitPulse benötigt einen **Fine-Grained Personal Access Token** (PAT).

### Token erstellen

1. GitHub → Settings → Developer Settings → Personal Access Tokens → **Fine-grained tokens**
2. "Generate new token"
3. **Repository access**: Nur deine Repos auswählen
4. **Permissions** (Repository):
   - Issues: Read
   - Pull requests: Read
   - Contents: Read (für Releases)
   - Actions: Read (für CI-Runs)
   - Metadata: Read (automatisch, für Watch-Repos)
5. Token kopieren und in den Add-on-Einstellungen eintragen

### Empfohlene Ablaufzeit

90 Tage (GitPulse warnt 14 Tage vor Ablauf im Dashboard).

---

## Konfigurationsoptionen

| Option | Beschreibung | Standard |
|--------|-------------|---------|
| `username` | Login-Benutzername | `admin` |
| `password` | Login-Passwort | `secret` |
| `session_hours` | Session-Dauer in Stunden | `24` |
| `github_token` | Fine-Grained PAT | — |
| `my_repos` | Eigene Repos (PRs/Issues/CI) | — |
| `watch_repos` | Repos nur für Release-Tracking | — |
| `include_ha_betas` | HA Beta/RC-Releases anzeigen | `true` |
| `poll_interval` | Abfrage-Intervall in Sekunden (min. 60) | `300` |
| `verbose_log` | Ausführliches Logging | `false` |
| `telegram_bot_token` | Telegram Bot Token (optional) | — |
| `telegram_chat_id` | Telegram Chat ID (optional) | — |

---

## Tabs

- **Pull Requests** — Alle offenen PRs inkl. Labels, Autor, Draft-Status
- **Issues** — Alle offenen Issues inkl. Labels
- **CI / Actions** — Die letzten 10 Workflow-Runs pro Repo
- **Releases** — Neuestes Release aller Watch-Repos; neue Releases werden rot markiert
- **Console** — Internes Log (entspricht dem HA-Add-on-Log)

---

## PWA / Cloudflare Tunnel

GitPulse funktioniert als Progressive Web App. Bei Betrieb hinter einem Cloudflare Tunnel sind keine zusätzlichen Einstellungen erforderlich — die No-Cache-Header für `manifest.json` und `sw.js` sind bereits gesetzt.
