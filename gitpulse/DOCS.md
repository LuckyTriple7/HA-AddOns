# GitPulse — Dokumentation

## Inhaltsverzeichnis

1. [GitHub Token](#github-token)
2. [Konfigurationsreferenz](#konfigurationsreferenz)
3. [Tabs & Features](#tabs--features)
4. [Telegram-Benachrichtigungen](#telegram-benachrichtigungen)
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

**Token erstellen:**

1. GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens
2. „Generate new token"
3. **Resource owner**: dein Account
4. **Repository access**: „Only select repositories" → eigene Repos wählen
5. Berechtigungen wie oben setzen → „Generate token"
6. Token kopieren und in der Add-on-Konfiguration unter `github_token` eintragen

**Empfohlene Ablaufzeit**: 90 Tage — GitPulse warnt 14 Tage vor Ablauf mit einem gelben Badge im Header.

> Watch-Repos (Release-Tracking externer Repos) benötigen nur öffentlichen Zugriff — dafür braucht der Token keine speziellen Rechte auf diese Repos.

---

## Konfigurationsreferenz

| Option | Standard | Beschreibung |
|---|---|---|
| `username` | `admin` | Login-Benutzername (nur relevant bei direktem Zugang auf Port 17792) |
| `password` | `secret` | Login-Passwort (nur relevant bei direktem Zugang auf Port 17792) |
| `session_hours` | `24` | Sitzungsdauer in Stunden vor erneuter Anmeldung |
| `github_token` | — | Fine-Grained PAT (siehe oben) |
| `my_repos` | — | Eigene Repos als `owner/repo` — vollständiges Monitoring (PRs, Issues, CI, Releases) |
| `watch_repos` | `home-assistant/core` | Nur Release-Tracking, kein Schreibzugriff erforderlich |
| `include_ha_betas` | `true` | HA Beta/RC-Releases im Releases-Tab anzeigen |
| `poll_interval` | `300` | Abfrageintervall in Sekunden (Minimum 10, empfohlen 30–300) |
| `verbose_log` | `false` | Detailliertere Logging-Ausgabe bei jedem Poll-Zyklus |
| `workflow_run_limit` | `25` | Maximale Anzahl geladener Workflow-Runs pro Repo (Maximum 50) |
| `telegram_bot_token` | — | Telegram-Bot-Token für Benachrichtigungen (leer = deaktiviert) |
| `telegram_chat_id` | — | Telegram-Chat-ID für Benachrichtigungen |
| `webhook_secret` | — | Webhook-Secret für GitHub Webhooks (leer = Webhooks vollständig deaktiviert) |

### Hinweise

**`my_repos`** — Repos können alternativ direkt im Dashboard über den ⚙-Button verwaltet werden. Die Dashboard-Konfiguration wird in `/data/gitpulse_repos.json` gespeichert und überlebt Add-on-Updates dauerhaft. Sobald diese Datei existiert, wird `my_repos` aus den HA-Optionen ignoriert.

**`poll_interval`** — Mit aktivierten Webhooks kann ein höherer Intervall (z. B. 300 Sekunden) gesetzt werden, da Updates sofort ankommen. Das Polling bleibt als Fallback erhalten.

**`workflow_run_limit`** — Höhere Werte bedeuten mehr API-Aufrufe pro Poll-Zyklus. Bei vielen Repos und niedrigem Poll-Intervall kann das Rate-Limit schneller erreicht werden.

---

## Tabs & Features

### Repos (Startseite)

Übersicht aller eigenen Repos auf einen Blick:

- Offene PRs und Issues mit Klick-Navigation in den jeweiligen Detail-Tab
- Letzter CI-Run mit Status
- **Stars ⭐, Forks 🍴, Watchers 👁** als kompakte Statistikzeile — Änderungen lösen Telegram-Benachrichtigungen aus
- Repo-Name als Link — öffnet GitHub im neuen Tab

### Pull Requests

- Liste aller offenen PRs über alle eigenen Repos
- **Review-Status** je PR: ✓ Approved / ✗ Changes requested / ○ Ausstehend
- **Kommentaranzahl** (PR-Kommentare + Review-Kommentare)
- Aktionen: PR auf GitHub öffnen · **Mergen** (Merge / Squash / Rebase) · **💬 Kommentieren**
- **Suche/Filter**: Live-Filter nach Titel, Autor, Nummer oder Label — Trefferanzahl wird angezeigt

### Issues

- Liste aller offenen Issues über alle eigenen Repos
- Aktionen: Issue öffnen · **✕ Schließen** · **💬 Kommentieren**
- **Suche/Filter**: Live-Filter nach Titel, Autor, Nummer oder Label — Trefferanzahl wird angezeigt

### CI / Actions

- Workflow-Runs aller eigenen Repos (Anzahl über `workflow_run_limit` konfigurierbar, Standard 25)
- **Quickfilter**: Alle / Letzte Stunde / Letzte 6 Std. / Heute / Gestern — Treffer-/Gesamtanzahl wird angezeigt
- Zeitanzeige: Uhrzeit (HH:MM) + Laufzeit; bei älteren Runs wird das Datum vorangestellt
- Commit-Beschreibung füllt die volle Spaltenbreite
- **▾ Details**: klappt Jobs und Steps mit Einzellaufzeiten auf (on-demand, kein extra API-Call)
- Aktionen je Run: **▶ Neustarten** · **■ Stoppen** (laufende Runs) · **🗑 Löschen** (abgeschlossene Runs)
- **Workflow starten (Dispatch)**: Workflow + Branch auswählen; Branch-Dropdown wird von GitHub geladen, Default-Branch ist vorausgewählt
- **⭐ Workflow-Favoriten**: Im Dispatch-Modal „⭐ Favorit speichern" — speichert Workflow + Branch dauerhaft. Favoriten erscheinen als eigene Karte im CI-Tab und können mit **▶** sofort ausgelöst oder mit **🗑** gelöscht werden.

### Releases

- Neue Releases aller Watch-Repos und eigenen Repos
- **Grüner pulsierender Punkt** bei ungesehenen Releases
- „Als gelesen markieren" — Releases werden persistent als gesehen gespeichert
- HA Beta/RC-Releases optional einblenden (`include_ha_betas`)
- Telegram-Benachrichtigung bei neuen Releases

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

## Telegram-Benachrichtigungen

### Bot einrichten

1. In Telegram [@BotFather](https://t.me/BotFather) öffnen → `/newbot`
2. Namen und Username vergeben → Bot-Token kopieren
3. `/start` an den neuen Bot schicken
4. Chat-ID ermitteln: [@userinfobot](https://t.me/userinfobot) öffnen → Chat-ID aus der Antwort kopieren
5. Token (`telegram_bot_token`) und Chat-ID (`telegram_chat_id`) in der Add-on-Konfiguration eintragen

### Benachrichtigungstypen

| Ereignis | Inhalt |
|---|---|
| Add-on-Start | Zusammenfassung aller offenen PRs und Issues je Repo |
| Neuer PR | Titel, Autor, Branch, Link |
| Neues Issue | Titel, Autor, Link |
| Workflow gestartet | Name, Branch, Trigger, Autor, Commit-SHA |
| Workflow beendet | Name, Ergebnis (✅ / ❌ / ⏹ / ⏭ / ⏱) |
| Neues Release | Repo, Version, Link |
| Stars/Forks/Watchers | Vorher → Nachher mit Differenz |

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
- Workflow runs
- Pushes
- Branch or tag creation
- Branch or tag deletion
- Stars

### Schritt 4: Verbindung testen

Nach dem Speichern sendet GitHub automatisch ein `ping`-Event. Im GitPulse-Log (Console-Tab) erscheint:

```
[INFO] Webhook empfangen: ping [] für owner/repo
```

### Sicherheit

- Alle eingehenden Webhooks werden per **HMAC-SHA256** (`X-Hub-Signature-256`) verifiziert — nicht signierte oder falsch signierte Requests werden mit `403 Forbidden` abgewiesen.
- Ohne `webhook_secret` startet Port 17793 **nicht** — der Port bleibt geschlossen.
- **Duplikat-Schutz**: Webhook-Events werden sofort als gesehen markiert, sodass der nächste Poll keine doppelten Telegram-Benachrichtigungen auslöst.
- Das Polling bleibt als Fallback aktiv (z. B. wenn Webhooks verloren gehen).

### Verarbeitete Ereignistypen

| GitHub Event | Aktion |
|---|---|
| `pull_request` | Cache aktualisieren, Telegram bei neuem PR |
| `issues` | Cache aktualisieren, Telegram bei neuem Issue |
| `workflow_run` | Cache aktualisieren, Telegram bei Start/Ende |
| `push` | Cache aktualisieren |
| `create` / `delete` | Cache aktualisieren (Branches/Tags) |
| `star` / `fork` | Cache aktualisieren |
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
