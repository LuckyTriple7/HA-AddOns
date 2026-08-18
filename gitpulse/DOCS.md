# GitPulse — Dokumentation

## Inhaltsverzeichnis

1. [GitHub Token](#github-token)
2. [Konfigurationsreferenz](#konfigurationsreferenz)
3. [Tabs & Features](#tabs--features)
4. [Benachrichtigungen](#benachrichtigungen)
5. [GitHub Webhooks](#github-webhooks)
6. [Tipps & Hinweise](#tipps--hinweise)

---

## GitHub Token

GitPulse benötigt einen GitHub **Fine-Grained Personal Access Token (PAT)** mit folgenden Berechtigungen:

| Berechtigung | Stufe |
|---|---|
| Repository: Contents | Read |
| Repository: Metadata | Read |
| Repository: Pull Requests | Read and write |
| Repository: Issues | Read and write |
| Repository: Actions | Read and write |
| Repository: Dependabot alerts | Read |
| Repository: Secret scanning alerts | Read |
| Repository: Security events | Read |

**Token erstellen:**

1. GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens
2. „Generate new token"
3. **Resource owner**: dein Account
4. **Repository access**: „Only select repositories" → eigene Repos wählen
5. Berechtigungen wie oben setzen → „Generate token"
6. Token kopieren und in der Add-on-Konfiguration unter `github_token` eintragen

**Empfohlene Ablaufzeit**: 90 Tage — GitPulse warnt 14 Tage vor Ablauf mit einem gelben Badge im Header.

> Watch-Repos (Release-Tracking externer Repos wie z. B. `home-assistant/core`) benötigen nur öffentlichen Zugriff — dafür braucht der Token keine speziellen Rechte auf diese Repos.

---

## Konfigurationsreferenz

| Option | Standard | Beschreibung |
|---|---|---|
| `username` | `admin` | Login-Benutzername (nur relevant bei direktem Zugang auf Port 17792) |
| `password` | `secret` | Login-Passwort (nur relevant bei direktem Zugang auf Port 17792) |
| `session_hours` | `24` | Sitzungsdauer in Stunden vor erneuter Anmeldung |
| `github_token` | — | Fine-Grained PAT (siehe oben) |
| `my_repos` | — | Eigene Repos als `owner/repo` — vollständiges Monitoring (PRs, Issues, CI, Releases, Security) |
| `watch_repos` | `home-assistant/core` | Nur Release-Tracking; kein Schreibzugriff erforderlich |
| `include_ha_betas` | `true` | HA Beta/RC-Releases im Releases-Tab anzeigen |
| `poll_interval` | `300` | Abfrageintervall in Sekunden (Minimum 10, empfohlen 30–300) |
| `verbose_log` | `false` | Detailliertere Logging-Ausgabe je Poll-Zyklus |
| `workflow_run_limit` | `25` | Maximale Anzahl geladener Workflow-Runs pro Repo (Maximum 50) |
| `addon_manager` | `false` | Add-on-Manager-Tab aktivieren (Versions-Bump direkt aus der UI) |
| `digest_hour` | `-1` | Tages-Digest: Stunde (0–23), zu der täglich eine Zusammenfassung gesendet wird; `-1` = deaktiviert |
| `telegram_bot_token` | — | Telegram-Bot-Token für Benachrichtigungen (leer = deaktiviert) |
| `telegram_chat_id` | — | Telegram-Chat-ID für Benachrichtigungen |
| `webhook_secret` | — | Webhook-Secret für GitHub Webhooks (leer = Webhooks vollständig deaktiviert) |
| `smtp_host` | — | SMTP-Serveradresse für E-Mail-Benachrichtigungen |
| `smtp_port` | `587` | SMTP-Port (typischerweise 587 für STARTTLS, 465 für SSL) |
| `smtp_user` | — | SMTP-Benutzername |
| `smtp_password` | — | SMTP-Passwort |
| `smtp_to` | — | Empfänger-E-Mail-Adresse |
| `smtp_tls` | `true` | STARTTLS aktivieren |

### Hinweise

**`my_repos`** — Repos können alternativ direkt im Dashboard über den ⚙-Button verwaltet werden. Die Dashboard-Konfiguration wird in `/data/gitpulse_repos.json` gespeichert und überlebt Add-on-Updates dauerhaft. Sobald diese Datei existiert, wird `my_repos` aus den HA-Optionen ignoriert.

**`watch_repos`** — Nur für Release-Tracking geeignet (z. B. `home-assistant/core`, `Hyundai-Kia-Connect/kia_uvo`). PRs, Issues, CI und Security werden für Watch-Repos nicht abgefragt.

**`poll_interval`** — Mit aktivierten Webhooks kann ein höheres Intervall (z. B. 300 s) gesetzt werden, da Updates sofort ankommen. Das Polling bleibt als Fallback erhalten.

**`workflow_run_limit`** — Höhere Werte bedeuten mehr API-Aufrufe pro Poll-Zyklus. Bei vielen Repos und niedrigem Poll-Intervall kann das Rate-Limit schneller erreicht werden.

---

## Tabs & Features

### Repos (Startseite)

Übersicht aller eigenen Repos auf einen Blick:

- Offene PRs und Issues mit Klick-Navigation in den jeweiligen Detail-Tab
- Letzter CI-Run mit Status
- **Stars ⭐, Forks 🍴, Watchers 👁** als kompakte Statistikzeile — Änderungen lösen Benachrichtigungen aus
- **Insights-Zeile**: ⚖️ Lizenz · ⚙️ CI aktiv · 🔒 Security-Alert-Zähler (klickbar → Security-Tab) — fehlende Konfiguration auf einen Blick
- Repo-Name als Link — öffnet GitHub im neuen Tab

### Pull Requests

- Liste aller offenen PRs über alle eigenen Repos
- **Repo-Wechsler** oben im Tab: zwischen Repos umschalten; Zähler zeigt PRs je Repo
- **Review-Status** je PR: ✓ Approved / ✗ Changes requested / ○ Ausstehend
- **Kommentaranzahl** (PR-Kommentare + Review-Kommentare)
- **▼ Beschreibung**: PR-Body aufklappbar direkt in der Liste — Markdown wird gerendert (Überschriften, fett, Links, `- [x]` Checkboxen)
- **💬 Kommentarvorschau**: letzte 3 Kommentare on-demand ladbar — erneuter Klick schließt die Vorschau
- Aktionen: PR auf GitHub öffnen · **Mergen** (Merge / Squash / Rebase) · **PR schließen** · **💬 Kommentieren**
- **Suche/Filter**: Live-Filter nach Titel, Autor, Nummer oder Label · **Filter wird seitenübergreifend gespeichert** (localStorage)

### Issues

- Liste aller offenen Issues über alle eigenen Repos
- **Repo-Wechsler** oben im Tab (synchron mit PRs, CI und Security)
- **▼ Beschreibung**: Issue-Body aufklappbar — Markdown wird gerendert
- **💬 Kommentarvorschau**: letzte 3 Kommentare on-demand ladbar
- Aktionen: Issue öffnen · **✕ Schließen** · **💬 Kommentieren**
- **Suche/Filter**: Live-Filter nach Titel, Autor, Nummer oder Label · Filter wird gespeichert

### CI / Actions

- Workflow-Runs aller eigenen Repos (Anzahl über `workflow_run_limit` konfigurierbar)
- **Repo-Wechsler** oben im Tab (synchron mit PRs, Issues und Security)
- **Quickfilter**: Alle / Letzte Stunde / Letzte 6 Std. / Heute / Gestern
- Zeitanzeige: Uhrzeit (HH:MM) + Laufzeit; bei älteren Runs wird das Datum vorangestellt
- **▾ Details**: klappt Jobs und Steps mit Einzellaufzeiten auf (on-demand, kein extra API-Call)
- Aktionen je Run: **▶ Neustarten** · **■ Stoppen** (laufende Runs) · **🗑 Löschen** (abgeschlossene Runs)
- **Workflow starten (Dispatch)**: Workflow + Branch auswählen; Branch-Dropdown wird von GitHub geladen, Default-Branch ist vorausgewählt
- **⭐ Workflow-Favoriten**: Im Dispatch-Modal „⭐ Favorit speichern" — speichert Workflow + Branch dauerhaft. Favoriten erscheinen als eigene Karte im CI-Tab und können mit **▶** sofort ausgelöst oder mit **🗑** gelöscht werden.

### Releases

- Neue Releases aller eigenen Repos und Watch-Repos, aufgeteilt nach Kategorie
- **Grüner pulsierender Punkt** bei ungesehenen Releases
- „Als gelesen markieren" — Releases werden persistent als gesehen gespeichert
- HA Beta/RC-Releases optional einblenden (`include_ha_betas`)
- Benachrichtigungen bei neuen Releases (Telegram, E-Mail, Browser)

### Security

Alle offenen Security-Alerts aller eigenen Repos auf einen Blick:

- **Repo-Wechsler** oben im Tab (synchron mit PRs, Issues und CI)
- **🤖 Dependabot** — veraltete Dependencies mit Schwachstellen (Paket, Ecosystem, Summary, Fix-Version)
- **🔍 Code Scanning** — CodeQL-Findings (Tool, Regel, Beschreibung, Datei + Zeile)
- **🔑 Secret Scanning** — versehentlich eingecheckte Secrets

Schweregrad-Icons: 🔴 CRITICAL · 🟠 HIGH · 🟡 MEDIUM · 🟢 LOW

Die Kachel in der Stat-Leiste ist **rot** bei HIGH/CRITICAL oder Secret Scanning, **gelb** bei MEDIUM/LOW, **grün** bei 0 Alerts. Der Badge am Tab-Button blinkt bei neuen Alerts.

> Repos ohne Dependabot oder ohne Security-Features zeigen keinen Warn-Banner — GitPulse unterscheidet automatisch zwischen „Token fehlt Berechtigung" (🔒-Hinweis) und „Dependabot auf diesem Repo nicht aktiviert" (kein Hinweis).

**Voraussetzung**: PAT benötigt Dependabot-, Secret-Scanning- und Security-Events-Berechtigungen (siehe [GitHub Token](#github-token)).

### Meine Aktivität

Zeigt alle offenen PRs und Issues, die du selbst erstellt hast, sowie PRs bei denen du als Reviewer angefragt bist — repo-übergreifend:

- **Meine offenen Pull Requests** — alle eigenen offenen PRs in allen Repos (eigene und fremde)
- **Zur Review angefragt** — PRs bei denen du als Reviewer eingetragen bist (`review-requested:@me`)
- **Meine offenen Issues** — alle eigenen offenen Issues in allen Repos
- **▼ Beschreibung** + **💬 Kommentarvorschau** — wie in PRs/Issues-Tab
- **💬 Kommentar-Zähler** je Eintrag — neue Kommentare werden erkannt und lösen Benachrichtigungen aus; selbst verfasste Kommentare zählen nicht als ungelesen
- **Schließen-Button** — sichtbar nur für Repos in denen du Schreibzugriff hast (`my_repos`); mit Sicherheitsabfrage im Browser
- **Filter-Persistenz**: aktiver Repo-Wechsler und Suchtext werden in localStorage gespeichert und nach Reload wiederhergestellt
- Benachrichtigungen (Telegram, E-Mail, Browser) für neue eigene PRs/Issues, neue Kommentare und Review-Requests — separat abschaltbar

### Add-on Manager *(optional)*

Nur sichtbar wenn `addon_manager: true` in den Add-on-Einstellungen.

Ermöglicht es, Versions-Bumps für HA Add-ons direkt aus der GitPulse-UI vorzunehmen:

- Alle Add-ons im konfigurierten Repo werden geladen (Erkennung über `config.yaml`)
- **+Dep** — Dependabot-Stil: letzte Stelle erhöhen (`1.5.6 → 1.5.6.1`)
- **+Patch** — manuell: Patch-Version erhöhen (`1.5.6 → 1.5.7`, `1.5.6.1 → 1.5.7`)
- CHANGELOG-Eintrag schreiben; aus geschlossenen PRs befüllen
- Commit & Push direkt aus der UI — Image-Verfügbarkeit wird nach dem Build geprüft

### Console

- Internes Live-Log des Add-ons mit Autoscroll
- Nützlich für Debugging, Rate-Limit-Status und Webhook-Empfangsbestätigungen

### Header

- **Token-Badge**: grün (gültig) / gelb (<14 Tage bis Ablauf) / rot (<5 Tage); Mouseover zeigt Ablaufdatum
- **Rate-Limit-Badge**: verbleibende GitHub API-Aufrufe; grün (>500) / gelb (<500) / rot (<200); Mouseover zeigt Reset-Zeit
- **↻ Jetzt abfragen**: manueller Poll aller Repos
- **⚙ Repos verwalten**: Repos direkt in der UI hinzufügen/entfernen (persistent)
- **Dark / Light Mode** · **DE / EN Sprachwechsel**

---

## Benachrichtigungen

GitPulse unterstützt drei unabhängige Benachrichtigungskanäle: **Telegram**, **E-Mail (SMTP)** und **Browser-Benachrichtigungen**. Jeder Kanal kann pro Ereignistyp einzeln aktiviert oder deaktiviert werden (⚙ → Einstellungen → Telegram / E-Mail / Browser).

### Telegram

#### Bot einrichten

1. In Telegram [@BotFather](https://t.me/BotFather) öffnen → `/newbot`
2. Namen und Username vergeben → Bot-Token kopieren
3. `/start` an den neuen Bot schicken
4. Chat-ID ermitteln: [@userinfobot](https://t.me/userinfobot) öffnen → Chat-ID aus der Antwort kopieren
5. Token (`telegram_bot_token`) und Chat-ID (`telegram_chat_id`) in der Add-on-Konfiguration eintragen

### E-Mail (SMTP)

SMTP-Zugangsdaten (`smtp_host`, `smtp_port`, `smtp_user`, `smtp_password`, `smtp_to`, `smtp_tls`) in der Add-on-Konfiguration eintragen. Eine Test-E-Mail kann über ⚙ → E-Mail → „Test-E-Mail senden" verschickt werden.

### Browser-Benachrichtigungen

Benachrichtigungen werden direkt im Browser angezeigt (Desktop-Benachrichtigungen). Beim ersten Mal muss die Browser-Berechtigung erteilt werden. Benachrichtigungen können einzeln pro Ereignistyp aktiviert/deaktiviert und für 1 Stunde, 4 Stunden oder bis morgen stummgeschaltet werden.

### Ereignistypen

| Ereignis | Inhalt |
|---|---|
| Add-on-Start | Zusammenfassung aller offenen PRs und Issues je Repo |
| Neuer PR | Titel, Autor, Branch, Link |
| PR geschlossen / gemerged | Titel, Ergebnis, Link |
| Neues Issue | Titel, Autor, Link |
| Workflow gestartet | Name, Branch, Trigger, Autor, Commit-SHA |
| Workflow beendet | Name, Ergebnis (✅ / ❌ / ⏹ / ⏭ / ⏱) |
| Neues Release | Repo, Version, Link |
| Stars/Forks/Watchers | Vorher → Nachher mit Differenz |
| 🚨 Secret Scanning Alert | Typ, Alert-Nr., Aktion, Link |
| 🔴 Code Scanning Alert | Schweregrad, Tool, Regel, Datei:Zeile, Link |
| 🟠 Dependabot Alert | Schweregrad, Paket, Ecosystem, Summary, Fix-Version, Link |
| 👤 Meine Aktivität | Neuer eigener PR oder Issue |
| 💬 Neue Kommentare | Neuer Kommentar an PR/Issue — eigene Kommentare lösen nichts aus |
| 🔍 Review-Request | Du wurdest als Reviewer für einen PR angefragt |
| 📋 Tages-Digest | Tägliche Zusammenfassung (konfigurierbar via `digest_hour`) |

### Tages-Digest

Der Tages-Digest sendet einmal täglich eine Zusammenfassung aller offenen PRs, Issues und Security-Alerts — ergänzend zu den Echtzeit-Benachrichtigungen.

**Konfiguration**: `digest_hour` auf eine Stunde zwischen `0` und `23` setzen (z. B. `8` = 08:00 Uhr morgens). Der Wert `-1` deaktiviert den Digest.

**Inhalt der Nachricht:**

```
📋 GitPulse Tages-Digest — 10.06.2026

• home-assistant/core — 42 PRs, 15 Issues · 🔒 2 Alerts
• LuckyTriple7/HA-AddOns — 1 PR, 0 Issues

Gesamt: 43 PRs, 15 Issues, 🔒 2 Alerts
```

> Der Digest liest den **aktuellen Stand** beim Senden — er summiert keine Ereignisse über den Tag. Das Add-on muss zur konfigurierten Uhrzeit laufen; verpasste Stunden werden nicht nachgeholt.

---

## GitHub Webhooks

Webhooks ermöglichen Echtzeit-Updates: Statt bis zu 5 Minuten auf den nächsten Poll zu warten, empfängt GitPulse das GitHub-Event direkt und aktualisiert das Dashboard in unter einer Sekunde.

### Voraussetzungen

- Eine von außen erreichbare Domain (z. B. `webhook.example.com`)
- SSL-Zertifikat (GitHub sendet ausschließlich HTTPS)
- Nginx o. ä. als Reverse-Proxy von HTTPS auf den internen Port 17793

### Schritt 1: Webhook-Secret generieren

```bash
openssl rand -hex 32
```

Das Secret in der Add-on-Konfiguration unter `webhook_secret` eintragen. **Das Add-on startet den Webhook-Listener auf Port 17793 ausschließlich wenn ein Secret konfiguriert ist** — ohne Secret läuft nur das normale Polling.

### Schritt 2: Nginx konfigurieren

```nginx
server {
    listen 443 ssl;
    server_name webhook.example.com;

    ssl_certificate     /etc/letsencrypt/live/webhook.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/webhook.example.com/privkey.pem;

    location / {
        proxy_pass http://homeassistant:17793;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 30s;
    }
}
```

### Schritt 3: Webhook in GitHub einrichten

Für jedes Repo unter **Settings → Webhooks → Add webhook**:

| Feld | Wert |
|---|---|
| Payload URL | `https://webhook.example.com/webhook` |
| Content type | `application/json` |
| Secret | Das Secret aus Schritt 1 (identisch!) |
| SSL verification | Enable SSL verification |
| Events | „Let me select individual events" |

Empfohlene Events:

- Pull requests
- Issues
- Issue comments
- Pull request review comments
- Workflow runs
- Pushes
- Branch or tag creation / deletion
- Stars
- Secret scanning alerts
- Code scanning alerts
- Dependabot alerts

### Schritt 4: Verbindung testen

Nach dem Speichern sendet GitHub automatisch ein `ping`-Event. Im GitPulse-Log (Console-Tab) erscheint:

```
[INFO] Webhook empfangen: ping [] für owner/repo
```

### Sicherheit

- Alle eingehenden Webhooks werden per **HMAC-SHA256** (`X-Hub-Signature-256`) verifiziert — nicht signierte oder falsch signierte Requests werden mit `403 Forbidden` abgewiesen.
- Ohne `webhook_secret` startet Port 17793 **nicht** — der Port bleibt geschlossen.
- **Duplikat-Schutz**: Webhook-Events werden sofort als gesehen markiert, sodass der nächste Poll keine doppelten Benachrichtigungen auslöst.
- Das Polling bleibt als Fallback aktiv (z. B. wenn Webhooks verloren gehen).

### Verarbeitete Ereignistypen

| GitHub Event | Aktion |
|---|---|
| `pull_request` | Cache aktualisieren, Benachrichtigung bei neuem PR |
| `issues` | Cache aktualisieren, Benachrichtigung bei neuem Issue |
| `issue_comment` / `pull_request_review_comment` | Sofortige Benachrichtigung bei fremdem Kommentar (eigene bleiben stumm) |
| `workflow_run` | Cache aktualisieren, Benachrichtigung bei Start/Ende |
| `push` | Cache aktualisieren |
| `create` / `delete` | Cache aktualisieren (Branches/Tags) |
| `star` / `fork` | Cache aktualisieren |
| `secret_scanning_alert` | Sofortige Benachrichtigung — immer, auch vor erstem Poll |
| `code_scanning_alert` | Benachrichtigung bei `created` / `appeared_in_branch` / `reopened` |
| `dependabot_alert` | Benachrichtigung bei `created` / `reopened` / `reintroduced` |
| `ping` | Verbindungsbestätigung (keine weitere Aktion) |

---

## Tipps & Hinweise

**PWA / Cloudflare Tunnel**: GitPulse funktioniert als Progressive Web App hinter Cloudflare Tunnel und HA Cloud. `manifest.json` und `sw.js` werden mit `No-Cache`-Headern ausgeliefert, `crossorigin="use-credentials"` ist am Manifest-Link gesetzt.

**Rate-Limit**: Das GitHub API erlaubt 5.000 Anfragen pro Stunde. GitPulse passt den Poll-Intervall automatisch an: bei < 500 verbleibenden Calls wird verdoppelt, bei < 100 verdreifacht, bei Erschöpfung wird bis zum API-Reset gewartet. ETag-Support (`If-None-Match`) reduziert die Anzahl der zählenden Anfragen bei unveränderten Daten auf null.

**Persistent gespeicherte Daten**:

| Datei | Inhalt |
|---|---|
| `/data/gitpulse_repos.json` | Repo-Liste (aus ⚙-Manager) |
| `/data/workflow_favorites.json` | Workflow-Favoriten |
| `/data/seen_releases.json` | Als gelesen markierte Releases |
| `/data/seen_activity.json` | Bereits benachrichtigte eigene PRs/Issues (Meine Aktivität) |
