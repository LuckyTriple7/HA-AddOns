# Changelog

## [0.3.19] - 2026-06-11

### Fixed
- **Security Autofix**: Warnschwelle auf `ahead_by > 0` gesenkt — bereits 1 Commit auf dev kann die falsche Dateiversion einspielen

## [0.3.18] - 2026-06-11

### Added
- **Security Autofix**: Warnung wenn `dev` mehr als 5 Commits vor `main` liegt — Autofix könnte ältere Dateiversion einspielen; `confirm()`-Dialog erlaubt trotzdem fortzufahren

## [0.3.17] - 2026-06-11

### Fixed
- **Security Autofix**: Branch wird jetzt vor dem Commit-Schritt explizit angelegt (`POST /git/refs`) — GitHub-API setzt existierende Branch voraus und erstellt sie nicht selbst

## [0.3.16] - 2026-06-11

### Fixed
- **Security Autofix**: Ladeanzeige und Fehlermeldungen jetzt vollständig übersetzt (DE/EN) statt hardcodiertem Deutsch; Backend gibt error_code zurück, Frontend übersetzt

## [0.3.15] - 2026-06-11

### Fixed
- **Security Autofix**: 422-Fehler wird jetzt klar erklärt ("Kein Autofix verfügbar für diesen Alert-Typ"); API-Aufruf wieder aktiv — Token braucht Schreibrechte auf "Code scanning alerts" + "Code quality"

## [0.3.14] - 2026-06-11

### Changed
- **Security-Tab**: 🤖 Fix-Button öffnet jetzt direkt die GitHub-Alert-Seite (Copilot Autofix per UI auslösbar) statt API-Aufruf — die API erfordert Copilot Enterprise, die UI funktioniert mit jedem Copilot-Plan; der resultierende Branch erscheint danach automatisch im Branch-Manager

## [0.3.13] - 2026-06-11

### Fixed
- **Webhook**: Security-Events (`code_scanning_alert`, `dependabot_alert`, `secret_scanning_alert`) lösen jetzt sofort einen Repo-Poll aus — die UI aktualisiert sich direkt nach dem Webhook, ohne auf den nächsten geplanten Poll zu warten

## [0.3.12] - 2026-06-11

### Added
- **Security-Tab**: 🤖 Fix-Button bei jedem Code-Scanning-Alert (CodeQL) — generiert via GitHub Copilot Autofix API einen Fix und committet ihn in einen neuen Branch (`codeql/autofix-{n}-{ts}`); Branch erscheint dann im Branch-Manager mit Merge-Status
- Erfordert GitHub Advanced Security oder Copilot; bei fehlendem Zugriff erscheint eine verständliche Fehlermeldung

## [0.3.11] - 2026-06-11

### Fixed
- **Branch-Manager**: SyntaxError durch einfache Anführungszeichen in Bestätigungstexten behoben (`| tojson` im Template)

## [0.3.10] - 2026-06-11

### Added
- **Branch-Manager**: Merge-Status und PR-Info pro Branch
  - ✅ "in main" — Branch ist vollständig in main/dev gemergt → sicher zu löschen
  - ⚠ "PR #N" — Branch hat einen offenen PR → Löschen zeigt explizite Warnung, dass der PR nicht mehr mergebar wird
  - ↑ "N nicht gemergt" — Branch hat Commits die noch nicht in main/dev sind
  - Status wird parallel via GitHub Compare-API abgefragt (schnell auch bei vielen Branches)
  - Bulk-Löschen warnt zusätzlich wenn Branches mit offenen PRs ausgewählt sind

## [0.3.9] - 2026-06-11

### Added
- **Branch-Manager** im Cherry-Pick-Tab: alle Branches eines Repos auflisten, einzeln oder per Mehrfachauswahl löschen; `main`, `master`, `dev`, `develop` sind geschützt (🔒) und können nicht gelöscht werden
- **Cherry-Pick-Tab** in der Navigationsleiste nach "Add-on Releases" verschoben (war zuvor nach "Activity")

## [0.3.8] - 2026-06-11

### Fixed
- **Security-Tab**: `ghLink is not defined` Konsolenfehler behoben — `onclick`-Attribut entfernt, Links öffnen via `href`/`target="_blank"` nativ

## [0.3.7] - 2026-06-11

### Fixed
- **Cherry-Pick**: Merge-Commits (z.B. "chore: merge dev → main") werden jetzt als solche markiert und standardmäßig **nicht** ausgewählt — sie enthalten hunderte Dateien und sind für Cherry-Pick ungeeignet
- **Cherry-Pick**: 120s Timeout im Browser mit verständlicher Meldung statt endlosem "Läuft…"

## [0.3.6] - 2026-06-11

### Added
- **Cherry-Pick-Tab**: neuer Tab zum Übernehmen einzelner Commits von einem Branch in einen anderen — Quell-Branch wählen, Commits auswählen, PR direkt nach dev/main erstellen; ideal für CodeQL-Fix-Branches die auf `main` zielen, aber zuerst nach `dev` sollen

## [0.3.5] - 2026-06-10

### Fixed
- **CI-Tab**: Laufzeit aktiver Workflow-Runs aktualisiert sich jetzt sekündlich live (vorher statischer Wert vom letzten Poll)
- **CI-Tab**: ▾-Pfeil dreht sich beim Aufklappen der Job-Details um 180°

## [0.3.4] - 2026-06-10

### Fixed
- **"▼ Beschreibung"-Button** hatte schwarze Schrift im Dark Mode: `color:var(--muted)` Fallback `#8b949e` ergänzt, damit die Farbe auch im HA-Ingress korrekt aufgelöst wird

## [0.3.3] - 2026-06-10

### Changed
- **Body-Expand**: Markdown wird jetzt gerendert statt als Rohtext angezeigt — `## Überschriften`, `**fett**`, `[Links](url)` klickbar, `- [x]` Checkboxen mit ☑/☐, Inline-Code mit Hintergrund; linker Akzentstreifen für bessere visuelle Abgrenzung

## [0.3.2] - 2026-06-10

### Fixed
- **"▼ Beschreibung"-Button** zeigte "undefined": `T.pr_body_show` / `T.pr_body_hide` fehlten im JS-Übersetzungsobjekt `T`
- **SyntaxError beim Klick auf Beschreibungs-Button**: `JSON.stringify(bkey)` in `onclick="..."` erzeugte doppelte Anführungszeichen im HTML-Attribut → Browser bricht das Attribut vorzeitig ab → `toggleBody(` unvollständig; ersetzt durch `safeJsArg(bkey)` (verwendet `&quot;`)
- **Kommentare-Toggle**: erneuter Klick auf Kommentare-Button schließt die Vorschau jetzt wieder
- **`no_activity`** ins T-Objekt ergänzt (war Jinja2-direkt, jetzt konsistent)

## [0.3.1] - 2026-06-10

### Fixed
- **Kommentare-Button** in Meine Aktivität, PRs und Issues tat nichts: `CSS.escape()` erzeugte Backslash-IDs in HTML-Attributen (`hacs\/default\#8357`), die im JS-String-Kontext als Escape-Sequenzen interpretiert wurden → `getElementById` fand das Element nie; ersetzt durch `mkId()` (nur `[a-zA-Z0-9_-]`)
- **Body-Expand-Button** (▼ Beschreibung) im Aktivitäts-Tab ebenfalls durch denselben ID-Bug betroffen
- **"undefined" als Label-Chip**: `escHtml(null/undefined)` erzeugte `"null"`/`"undefined"` als Text; `labelColor(null)` crashte; beide Funktionen abgesichert, Label-Arrays mit `.filter(Boolean)` gefiltert
- **Fehlende Übersetzung**: `tg_review_request` und `tg_digest` in `en.json` ergänzt (Toggle-Beschriftung in den Einstellungen war leer)

## [0.3.0] - 2026-06-10

### Added
- **Filter-Persistenz**: aktiver Repo-Wechsler und Suchtext je Tab werden in localStorage gespeichert und nach Seiten-Reload wiederhergestellt
- **Review-Requests**: neuer Bereich „Zur Review angefragt" in Meine Aktivität — PRs bei denen du als Reviewer angefragt bist (`review-requested:@me`) mit Benachrichtigung
- **Body-Expand**: PR- und Issue-Beschreibung aufklappbar direkt in der Liste (▼ Beschreibung)
- **Inline-Kommentarvorschau**: Letzte 3 Kommentare eines PR/Issue on-demand ladbar (neuer `/api/comments`-Endpunkt, gecacht im Browser bis Reload)
- **Tages-Digest E-Mail**: tägliche Zusammenfassung aller offenen PRs, Issues und Security-Alerts — konfigurierbar via `digest_hour` (0–23, -1 = deaktiviert); ergänzt Echtzeit-Benachrichtigungen
- **Repo-Insights-Ampel**: neue Zeile in jedem Repo-Card — Lizenz (⚖️), CI aktiv (⚙️) und Security-Alert-Zähler (🔒) auf einen Blick; Security-Zähler ist klickbar

### Changed
- `no_activity`-Text aktualisiert (enthält jetzt Review-Requests)
- Benachrichtigungstypen `review_request` und `digest` in TG/E-Mail/Browser-Einstellungen wählbar

## [0.2.1] - 2026-06-10

### Fixed
- Security: Dependabot-API gibt für public Repos ohne aktiviertes Dependabot 403 (statt 404) zurück — Response-Message wird jetzt ausgewertet, um echten Scope-Fehler von "nicht aktiviert" zu unterscheiden; kein falscher 🔒-Hinweis mehr

## [0.2.0] - 2026-06-10

### Fixed
- JavaScript-Syntaxfehler (überzähliges `)`) in Security-Tab behoben — UI war seit v0.1.99 komplett leer

## [0.1.99] - 2026-06-10

### Fixed
- Security: 403 (fehlender Scope) und 404 (Dependabot nicht aktiviert) werden jetzt unterschieden — 🔒-Hinweis erscheint nur noch bei echtem Scope-Fehler, nicht wenn Dependabot schlicht nicht eingerichtet ist

## [0.1.98] - 2026-06-09

### Fixed
- Meine Aktivität: Schließen-Button nur für eigene Repos (`my_repos`) sichtbar — fremde Repos haben keine API-Schreibrechte

## [0.1.97] - 2026-06-09

### Added
- Meine Aktivität: Kommentar-Benachrichtigungen via Telegram, E-Mail und Browser wenn jemand einen eigenen PR oder Issue kommentiert (kein extra API-Call — nutzt `comments`-Zähler aus Search API)
- Meine Aktivität: Kommentar-Anzahl wird direkt in der Item-Zeile angezeigt (💬)

## [0.1.96] - 2026-06-09

### Fixed
- Meine Aktivität: GitHub Search API 422 — Leerzeichen statt `+` als Query-Separator (requests enkodiert `+` zu `%2B`)
- Meine Aktivität: `undefined` beim ersten Render — `my_activity` in `_gh_cache`-Initialisierung ergänzt

## [0.1.95] - 2026-06-09

### Added
- Neuer Tab "Meine Aktivität": zeigt alle offenen PRs und Issues die der authentifizierte GitHub-User erstellt hat, quer über alle Repos
- Summary-Kachel für eigene Aktivität mit Blink-Effekt bei neuen Einträgen
- Benachrichtigungen (Telegram, E-Mail, Browser) für neue eigene PRs/Issues — separat abschaltbar

## [0.1.94] - 2026-06-09

### Fixed
- `mobile-web-app-capable` Meta-Tag ergänzt (Deprecation-Warnung im Browser behoben)

## [0.1.93] - 2026-06-09

### Added
- Workflows (CI) und Security: Repo-Wechsler-Chips — alle vier Tabs (PRs, Issues, CI, Security) zeigen denselben Selektor und sind synchron

## [0.1.92] - 2026-06-09

### Added
- Releases-Tab: Eigene Repos (`my_repos`) werden jetzt oben als eigener Abschnitt angezeigt, Watch-Repos darunter
- Issues-Tab: Repo-Wechsler-Chips (wie im PR-Tab) — bei mehreren Repos direkt im Issues-Tab umschaltbar

### Fixed
- `_no_release_repos`: Repos ohne Releases werden nach 1 Stunde erneut geprüft statt dauerhaft bis Neustart übersprungen

## [0.1.91.1] - 2026-06-09

chore(deps): Bump requests from 2.33.0 to 2.34.2 in /gitpulse

## [0.1.91] - 2026-06-09

### Fixed
- CI/Actions: Aufgeklappte Job-Details bleiben nach Poll erhalten — expanded Run-IDs werden in einer Map gespeichert und nach dem Re-Render wiederhergestellt

## [0.1.90] - 2026-06-09

### Security
- Image-Check: `elif startswith('ghcr.io/')` via `urlparse(f'https://{image}')` ersetzt (CodeQL: Incomplete URL substring sanitization #134)
- Image-Check: Längen-Check (>300) + bounded Regex `{0,99}` statt `+` verhindert ReDoS (CodeQL: Polynomial ReDoS #134)

## [0.1.89] - 2026-06-09

### Fixed
- CI/Actions: Webhook-Repo-Poll (`_trigger_repo_poll`) ersetzte den Run-Cache mit frischen 500 Runs — jetzt wird auch dort gemergt, nicht ersetzt

## [0.1.88] - 2026-06-09

### Fixed
- CI/Actions: Workflow-Liste wächst nach dem initialen Load nicht mehr auf 500 zurück — beim initialen Start werden bis zu 500 Runs geladen, bei jedem weiteren Poll werden neue Runs vorne eingefügt und bestehende Einträge aktualisiert statt ersetzt

## [0.1.87] - 2026-06-09

### Fixed
- Add-on Manager: PR-Picker schließt nach Auswahl wieder korrekt

## [0.1.86] - 2026-06-09

### Fixed
- Add-on Manager: +Dep rechnet jetzt korrekt von der aktuellen Version (1.0.8.1 → 1.0.8.2 statt 1.0.9.1)
- Add-on Manager: mehrere PR-Titel übernehmen überschreibt nicht mehr — jeder Eintrag wird in einer neuen Zeile angehängt

## [0.1.85] - 2026-06-09

### Fixed
- Add-on Manager: Overlays und Karten nicht mehr transparent — `var(--card)` → `var(--surf)`, `var(--fg)` → `var(--text)`, `var(--hover)` → `var(--surf2)` (alle drei waren undefiniert)

## [0.1.84] - 2026-06-09

### Fixed
- PR-Picker: "Titel übernehmen" Button funktioniert jetzt — PR-Daten werden per Index-Array referenziert statt als String im onclick-Attribut (JSON.stringify erzeugte doppelte Anführungszeichen die das HTML brachen)

## [0.1.83] - 2026-06-09

### Security
- Image-Check: URL-Validierung via `urlparse` + hostname-Check statt `startswith`-Substring (CodeQL: Incomplete URL substring sanitization)

## [0.1.82] - 2026-06-09

### Fixed
- Add-on Manager PR-Picker: Einträge haben jetzt festen Hintergrund (war transparent); separate Buttons "Titel übernehmen" / "Body übernehmen" statt Body-Klick auf die ganze Karte

## [0.1.81] - 2026-06-09

### Security
- Browser-Bestätigung vor: Issue schließen, Workflow-Run abbrechen, Workflow-Run löschen, Workflow deaktivieren

## [0.1.80] - 2026-06-09

### Added
- Add-on Manager: "Aus PR"-Button öffnet Overlay mit letzten geschlossenen PRs; Branch/Titel-Filter zeigt passende PRs für das jeweilige Add-on zuerst; Klick übernimmt PR-Body als Changelog-Eintrag

## [0.1.79] - 2026-06-09

### Fixed
- Add-on Manager: 404 von GHCR zeigt "✗ Image nicht verfügbar" (rot) statt "⏳ Build läuft noch" — 404 bedeutet nur dass das Image fehlt, nicht dass ein Build läuft

## [0.1.78] - 2026-06-09

### Added
- Pull Requests: "Schließen"-Button (✕) zum direkten Schließen eines PRs ohne Merge

## [0.1.77] - 2026-06-09

### Fixed
- Add-on Manager: Image-Check GHCR Token-Exchange nutzt jetzt `owner:token` als Basic-Auth (statt `:token`); behebt 403 auf Manifest-Anfragen

## [0.1.76] - 2026-06-09

### Fixed
- Add-on Manager: Image-Check unterscheidet jetzt 200/404/403 korrekt — 404 = Build läuft, 403 = kein Zugriff (Token-Problem), statt alles als "Build läuft" anzuzeigen

## [0.1.75] - 2026-06-09

### Fixed
- Add-on Manager: Image-Check nutzt GitHub PAT direkt als Bearer-Token gegen GHCR (kein Token-Exchange mehr); behebt 403-Fehler bei öffentlichen Paketen

## [0.1.74] - 2026-06-09

### Added
- Add-on Manager: Image-Check — zeigt direkt ob das Docker-Image für die aktuelle Version in GHCR verfügbar ist (✓ grün) oder der Build noch läuft (⏳)

## [0.1.73.1] - 2026-06-08

Bump python from 3.11-alpine to 3.14-alpine in /gitpulse

## [0.1.72] - 2026-06-09

### Added
- CI-Tab: aufklappbares Workflows-Panel zeigt alle Workflows mit Status-Badge (aktiv/deaktiviert/inaktiv); per Button direkt aktivieren oder deaktivieren ohne GitHub zu öffnen

## [0.1.71] - 2026-06-09

### Added
- Add-on Manager: Verlauf-Button öffnet die letzten 10 Commits eines Add-ons mit Version, Datum und Commit-Message; per "Wiederherstellen" + Bestätigung wird config.yaml + CHANGELOG.md auf den gewählten Stand zurückgesetzt (neuer Commit, kein git-revert)

## [0.1.70] - 2026-06-09

### Changed
- Add-on Manager: nach erfolgreichem Commit wird die Liste automatisch neu geladen (1,5 s Delay)

## [0.1.69] - 2026-06-09

### Fixed
- Add-on Manager: Commit & Push Button funktionslos — JSON.stringify erzeugte ungültige HTML-Attribute; auf safeJsArg() umgestellt

## [0.1.68] - 2026-06-09

### Fixed
- Add-on Manager: Repo-Dropdown zeigt nur noch `my_repos`, nicht mehr `watch_repos`

## [0.1.67] - 2026-06-09

### Fixed
- Add-on Manager: HA-Config-Label für `addon_manager` in translations/de.yaml + en.yaml ergänzt

### Added
- Add-on Manager: Quick-Buttons +Patch (1.5.6→1.5.7) und +Dep (1.5.6→1.5.6.1) neben dem Versionsfeld

## [0.1.66] - 2026-06-08

### Added
- Add-on Manager: Kachel zeigt Anzahl der gefundenen Add-ons nach dem Laden

## [0.1.65] - 2026-06-08

### Added
- Add-on Manager: neuer Tab zum Verwalten von Add-on-Versionen und CHANGELOG-Einträgen
- Config-Option `addon_manager` (default: false) zum Aktivieren des Features
- GitHub Git Trees API für atomare Commits (config.yaml + CHANGELOG.md in einem Commit)
- Bestätigungs-Dialog vor jedem Commit
- DE/EN Übersetzungen

## [0.1.64] - 2026-06-08

### Security
- Open Redirect: `next`-Parameter in `set_lang()` via `urlparse` validiert — nur relative Pfade erlaubt (CodeQL MEDIUM #132)

## [0.1.63] - 2026-06-08

### Security
- Cookie Injection: `cookie_lang` aus Literal statt URL-Parameter in `set_lang()` (CodeQL MEDIUM #48)

## [0.1.62] - 2026-06-08

### Security
- Information Exposure: Exception-Details (`str(e)`) nicht mehr in HTTP-Responses zurückgegeben; stattdessen generische `'internal error'`-Meldung + internes `log.exception()` (CodeQL #6–#11, #13, #124)

## [0.1.61] - 2026-06-08

### Removed
- PWA-Installationsbanner ausgeblendet (Browser-Installationshinweis in der Adressleiste ist ausreichend)

## [0.1.60] - 2026-06-08

### Added
- Browser-Benachrichtigungen: Vierter Tab „Browser" im Settings-Modal mit denselben 10 Kategorien wie Telegram/E-Mail
- Einstellungen werden in `localStorage` gespeichert (gerätelokal, kein Backend nötig)
- Tab und Checkboxen ausgegraut wenn Notification-Berechtigung nicht erteilt

### Fixed
- Stummschaltung konnte nicht aufgehoben werden — Glocken-Dropdown zeigt jetzt „Stummschaltung aufheben"-Button im Snooze-Zustand
- Browser-Benachrichtigungen wurden nur für Releases gefeuert — alle 10 Kategorien werden jetzt per client-seitigem Diff erkannt
- Erster Seitenladevorgang löst keine Benachrichtigungs-Flut mehr aus (`_bn_first`-Flag)

---

## [0.1.59] - 2026-06-08

### Changed
- Browser-Benachrichtigungen: Notification-Banner entfernt, stattdessen Glocken-Button im Header
- Glocken-Icon zeigt Status: 🔔 Aktiv (blau), 🔕 Stummgeschaltet (gelb), ⛔ Deaktiviert (ausgegraut)
- Snooze-Dropdown: 1 Stunde, 4 Stunden, Bis morgen (08:00), Deaktivieren
- Snooze-Zustand wird in localStorage gespeichert (bleibt nach Reload erhalten)
- Browser fragt beim ersten Laden automatisch nach Berechtigung (kein Banner mehr)

---

## [0.1.58] - 2026-06-08

### Added
- HA Add-on-Übersetzungen für alle 6 SMTP-Optionen (de + en): smtp_host, smtp_port, smtp_user, smtp_password, smtp_to, smtp_tls

---

## [0.1.57] - 2026-06-08

### Added
- E-Mail-Benachrichtigungen via SMTP (Python stdlib `smtplib`, keine neue Dependency)
- Neue Add-on-Optionen: `smtp_host`, `smtp_port` (Standard 587), `smtp_user`, `smtp_password`, `smtp_to`, `smtp_tls` (STARTTLS)
- Settings-Modal: Dritter Tab „E-Mail" mit denselben 10 Benachrichtigungs-Typen wie Telegram
- Test-E-Mail-Button im E-Mail-Tab mit sofortigem Feedback
- Tab und Checkboxen ausgegraut wenn SMTP nicht konfiguriert
- `_tg_em()` Hilfsfunktion: sendet Telegram + E-Mail in einem Aufruf, prüft je eigene Einstellungen

---

## [0.1.56] - 2026-06-08

### Changed
- Settings → Telegram-Tab: Checkboxen und Tab-Button werden ausgegraut wenn Bot-Token oder Chat-ID in den Add-on-Einstellungen fehlen; Hinweistext erklärt die fehlende Konfiguration

---

## [0.1.55] - 2026-06-08

### Changed
- Settings-Modal: Zwei Tabs „Repos" und „Telegram" — Fenster bleibt kompakt, keine langen Scroll-Seiten mehr

---

## [0.1.54] - 2026-06-08

### Added
- Settings-Modal: Neue Sektion „Telegram Benachrichtigungen" mit 10 einzeln schaltbaren Typen (Start, neue PRs, PR geschlossen, neue Issues, Workflow gestartet/beendet, Releases, Repo-Statistiken, Stars & Forks, Security Alerts)
- Einstellungen werden in `gitpulse_repos.json` gespeichert (Add-on-Updates-sicher); Bot-Token und Chat-ID bleiben in den Add-on-Optionen
- Alle `_send_telegram`-Aufrufe (Poll + Webhook) prüfen jetzt die jeweilige Einstellung

---

## [0.1.53] - 2026-06-08

### Fixed
- PR- und Issue-Tab: Trefferzähler wird jetzt immer angezeigt wenn Suchfeld aktiv ist (nicht nur wenn Einträge gefiltert wurden)

---

## [0.1.52] - 2026-06-08

### Added
- CI/Actions-Tab: Suchfeld filtert Runs nach Name, Branch, Actor, Commit-Message und Run-Nummer — Treffer-Zähler eingeblendet
- Security-Tab: Suchfeld filtert Dependabot-Alerts nach Paket/Zusammenfassung, Code-Scanning nach Beschreibung/Rule-ID/Pfad/Tool und Secret-Scanning nach Typ — Treffer-Zähler eingeblendet
- Repo-Wechsel setzt CI-Suchfeld zurück

---

## [0.1.51] - 2026-06-08

### Fixed
- "Poll abgeschlossen" und "Webhook-Repo-Poll abgeschlossen" nur noch bei aktivem `verbose_log` — erschienen bisher immer im Log

---

## [0.1.50] - 2026-06-08

### Added
- Webhook `pull_request closed`: PR sofort aus offener Liste entfernen, in geschlossene Liste einfügen + Telegram-Benachrichtigung (⎇ gemerged / ✕ geschlossen)
- Merge-Button: Spinner `⏳` + disabled während GitHub-Request, verhindert Doppelklick
- Issue schließen / Workflow abbrechen / Workflow wiederholen: Button sofort deaktiviert nach Klick, wird bei Fehler wiederhergestellt
- Settings-Modal: Token-Berechtigungs-Hinweis (repo, contents:write, security_events, actions:write)

---

## [0.1.49] - 2026-06-07

### Security / Fixed
- Webhook-Port 17793: WSGI-Wrapper blockiert jetzt alle Pfade außer `POST /webhook` mit 403 — das komplette GitPulse-UI war bisher auch auf Port 17793 erreichbar
- `GET /webhook` gibt nun `{"status":"webhook endpoint ready"}` zurück (zur einfachen Erreichbarkeitsprüfung)

---

## [0.1.48] - 2026-06-07

### Security
- Flask 3.0.3 → 3.1.3 (Dependabot-Alert behoben)

---

## [0.1.47] - 2026-06-07

### Added
- PRs + Issues: Offen/Geschlossen-Toggle über der Sucheingabe
- Geschlossene PRs (max. 50, sortiert nach letzter Aktivität): zeigt ⎇ Gemerged (lila) oder ✕ Geschlossen (rot)
- Geschlossene Issues (max. 50): zeigt Schließzeitpunkt, keine Aktions-Buttons
- Merge/Kommentar/Schließen-Buttons ausgeblendet bei geschlossenen Einträgen
- Locale: `filter_open`, `filter_closed`, `pr_merged`, `pr_closed`, `no_closed_prs`, `no_closed_issues` (DE + EN)

---

## [0.1.46] - 2026-06-07

### Fixed
- Webhook `workflow_run`: UI-Update kommt jetzt sofort wenn die Telegram-Nachricht eintrifft — Run-Status wird direkt im Cache gepatcht + SSE gefeuert, ohne auf den vollständigen GitHub-API-Poll zu warten
- Gleiches gilt für neue Runs (`requested`): werden sofort in die Run-Liste eingefügt

---

## [0.1.45] - 2026-06-07

### Changed
- Tab-Reihenfolge: Security jetzt direkt neben Issues (wie in den Stat-Kacheln)

---

## [0.1.44] - 2026-06-07

### Fixed
- Dependabot-Alerts: HTTP 400 bei `per_page=100&page=1` — Dependabot-API akzeptiert diese Kombination nicht; eigener Paginator mit `per_page=30` ohne expliziten `page`-Parameter, Pagination über Link-Header

---

## [0.1.43] - 2026-06-07

### Improved
- Refresh-Countdown wird sofort abgebrochen wenn ein Webhook-SSE-Update eintrifft — kein unnötiges Warten bei aktiven Webhooks

---

## [0.1.42] - 2026-06-07

### Added
- Security-Tab: Dependabot-Zugriffscheck — zeigt Hinweis wenn Token den Scope `security_events` fehlt (statt stiller leerer Liste)
- Locale: `security_dep_no_access` (DE + EN) mit Link-Hinweis zum Token-Bearbeiten

---

## [0.1.41] - 2026-06-07

### Fixed
- CI-Status-Filter: Übersetzungs-Keys (`ci_status_*`) fehlten im `T`-Objekt des Templates → Labels zeigten „undefined"

---

## [0.1.40] - 2026-06-07

### Added
- CI-Tab: Status-Filter-Zeile unter dem Zeitfilter — Laufend 🟡 / Erfolgreich 🟢 / Fehlerhaft 🔴 / Abgebrochen ⚫ kombinierbar mit Zeitfilter
- Repo-Wechsel setzt beide Filter (Zeit + Status) auf „Alle" zurück

---

## [0.1.39] - 2026-06-07

### Security
- Polynomial-Regex (ReDoS): `<([^>]+)>` → `<(https?://[^>\s]{1,2048})>` mit Längen-Limit pro Link-Header-Segment (CodeQL: py/polynomial-redos #5)
- Clear-text Logging: Token-Scopes/Ablauf nicht mehr als Rohwert geloggt — stattdessen int/bool-Repräsentation (CodeQL: py/clear-text-logging #27, #28, #29)
- XSS / Incomplete escaping: Issue-Kommentar-Button nutzt `safeJsArg()` statt manueller `replace(/'/g)` (CodeQL: js/incomplete-html-attribute-sanitization #75)

---

## [0.1.38] - 2026-06-07

### Added
- CI-Tab: Workflow-Runs-Limit von 50 auf 500 erhöht (Backend paginiert bis zu 5 Seiten × 100 Runs via GitHub API)
- CI-Tab: Frontend-Paginierung — bei mehr als 50 gefilterten Runs werden je 50 pro Seite angezeigt, mit Blättern-Steuerung (‹ / ›) und Seitenanzeige

---

## [0.1.37] - 2026-06-07

### Added
- Security-Tab: Filter-Bar mit Severity-Chips (🔴 Critical / 🟠 High / 🟡 Medium / 🟢 Low) und Typ-Chips (🤖 Dependabot / 🔍 Code Scanning / 🔑 Secrets) — jeweils mit Anzahl, mehrere Filter kombinierbar
- Severity-Badge in der Alertliste farbig hervorgehoben (Farbe je nach Schweregrad)
- Secret-Scanning-Alerts erhalten automatisch Schweregrad „Critical"

---

## [0.1.36] - 2026-06-07

### Fixed
- Security-Alerts: Limit von 50 auf bis zu 1000 erhöht (10 Seiten × 100 pro Seite via Paginierung) — `_gh_get_paginated` unterstützt jetzt eigene `params` (z.B. `state=open`)

---

## [0.1.35] - 2026-06-07

### Security
- XSS-Schwachstelle in PR-Buttons behoben: `JSON.stringify`-basiertes Escaping (`safeJsArg`) statt `escHtml+replace` für onclick-Argumente (CodeQL: Incomplete string escaping #111)
- Exception-Details nicht mehr an Client zurückgegeben: generische `internal_error`-Meldung statt `str(e)` (CodeQL: Information exposure #107)
- Clear-text logging: `secret_type` aus Secret-Scanning-Alert-Log entfernt; Taint-Flow in Repo-Poll-Log durch explizite int-Konvertierung gebrochen (CodeQL: #108, #109, #110)

---

## [0.1.34] - 2026-06-07

### Changed
- CI/Actions: Dispatch-Button umbenannt von „▶ Starten" → „▶ Workflow auswählen" (EN: „Select Workflow") — unterscheidet sich jetzt klar vom Favoriten-Button der einen bekannten Workflow direkt startet

---

## [0.1.33] - 2026-06-07

### Changed
- Version bump für HA Update-Erkennung

---

## [0.1.32] - 2026-06-07

### Added
- Neuer **Security-Tab** + **Security-Tile** in der Stat-Leiste: zeigt alle offenen Dependabot-, Code Scanning- und Secret Scanning-Alerts je Repo
- Tile-Farbe: grün (0 Alerts) / gelb (medium/low) / rot (high/critical oder Secret Scanning)
- Badge am Tab-Button + Blinken wenn neue Alerts hinzukommen
- Backend: `_fetch_security_alerts()` ruft `/dependabot/alerts`, `/code-scanning/alerts` und `/secret-scanning/alerts` ab (ETag-gecacht); 403/404 werden still ignoriert bis PAT-Rechte ergänzt sind
- Rendering: Alerts sortiert nach Typ (🤖 Dependabot / 🔍 Code Scanning / 🔑 Secret Scanning), je mit Schweregrad-Icon, Paket/Regel, Beschreibung, Datei+Zeile, Fix-Version und direktem Alert-Link
- **Voraussetzung PAT**: zusätzliche Berechtigungen „Dependabot alerts (read)", „Secret scanning alerts (read)" und „Security events (read)" im Fine-Grained Token eintragen

---

## [0.1.31] - 2026-06-07

### Added
- Webhook-Event `code_scanning_alert`: Telegram-Benachrichtigung bei CodeQL-Findings mit Schweregrad (🔴 critical / 🟠 high / 🟡 medium / 🟢 low), Tool-Name, Regel-Beschreibung, Datei+Zeile und Alert-Link; nur bei `created`, `appeared_in_branch`, `reopened`
- Webhook-Event `dependabot_alert`: Telegram-Benachrichtigung bei Dependabot-Schwachstellen mit Schweregrad, Paket-Name, Ecosystem, Advisory-Zusammenfassung und verfügbarem Fix-Version; nur bei `created`, `reopened`, `reintroduced`
- Alle drei Security-Alert-Events (`secret_scanning_alert`, `code_scanning_alert`, `dependabot_alert`) schreiben immer ein `log.warning` — sichtbar in der Console unabhängig von `verbose_log`

---

## [0.1.30] - 2026-06-07

### Added
- Webhook-Event `secret_scanning_alert`: GitPulse empfängt GitHub Secret Scanning Alerts und schickt sofort eine Telegram-Nachricht (🚨 gefunden / 🔓 öffentlich geleakt / ✅ behoben / ⚠️ validiert / 🔁 wieder geöffnet)
- Alert-Details: Repo, Alert-Nummer, Secret-Typ (z. B. „GitHub Personal Access Token"), Aktion und direkter Link zum Alert auf GitHub
- Kein `_first_poll_done`-Check — Security-Alerts werden immer sofort gesendet, auch beim Add-on-Start

---

## [0.1.29] - 2026-06-07

### Fixed
- Webhook-Server auf Port 17793 startet nur wenn `webhook_secret` konfiguriert ist — ohne Secret läuft ausschließlich Polling wie gewohnt

---

## [0.1.28] - 2026-06-07

### Fixed
- Webhook: ohne konfiguriertes `webhook_secret` werden eingehende Requests sofort mit `{"status":"disabled"}` beantwortet — kein unauthentifizierter Zugriff möglich; Polling läuft wie gewohnt weiter

---

## [0.1.27] - 2026-06-07

### Added
- **GitHub Webhook-Support**: GitPulse empfängt jetzt Push-Benachrichtigungen von GitHub auf Port 17793 (`POST /webhook`)
- Events: `pull_request`, `issues`, `workflow_run`, `push`, `create`, `delete`, `star`, `fork` — Cache wird sofort aktualisiert, SSE-Push an alle Browser, Telegram-Benachrichtigung innerhalb < 1 Sekunde
- HMAC-SHA256 Signatur-Prüfung (`X-Hub-Signature-256`) — neues Config-Feld `webhook_secret`
- Duplikat-Schutz: Webhook markiert PR/Issue/Run sofort als gesehen → nächster Poll feuert kein zweites Telegram
- Polling bleibt als 5-Minuten-Fallback erhalten (Webhooks können verloren gehen)
- Port 17793 in `config.yaml` eingetragen (nginx → `https://webhook.domain.de` → Port 17793)

---

## [0.1.26] - 2026-06-07

### Changed
- CI/Actions: Commit-Beschreibung füllt jetzt die volle Spaltenbreite (kein `max-width:340px` mehr)
- CI/Actions: Zeitanzeige zeigt Uhrzeit (HH:MM) + Dauer statt nur Relativzeit ("2 hr ago"); bei älteren Runs wird das Datum vorangestellt
- CI/Actions: Quickfilter-Buttons über den Runs — Alle / Letzte Stunde / Letzte 6 Std. / Heute / Gestern; aktiver Filter zeigt Treffer-/Gesamtanzahl

---

## [0.1.25] - 2026-06-07

### Added
- Neues Config-Feld `workflow_run_limit` (Standard 25, Maximum 50): steuert wie viele Workflow-Runs je Repo geladen werden — konfigurierbar in den HA Add-on-Einstellungen

---

## [0.1.24] - 2026-06-07

### Added
- Pull Requests: 💬 Kommentieren-Button je PR-Zeile (nutzt dieselbe Backend-Route wie Issues — GitHub behandelt PRs und Issues identisch)
- Such-/Filterleiste in Pull Requests und Issues: Live-Filter nach Titel, Autor, Nummer und Label; Trefferanzahl ("3 von 7") wird angezeigt; Löschen über Browser-× oder leeren des Feldes

---

## [0.1.23] - 2026-06-07

### Added
- Workflow-Favoriten: Im Dispatch-Modal "⭐ Favorit speichern" Button — speichert Workflow + Branch dauerhaft in `/data/workflow_favorites.json`
- Favoriten erscheinen im CI/Actions-Tab als eigene Karte über den Runs; per ▶-Button direkt auslösen, per 🗑-Button löschen
- Duplikat-Schutz: gleicher Workflow + Branch wird nicht doppelt gespeichert
- Backend: neue Routen `GET/POST /api/workflow/favorites` und `DELETE /api/workflow/favorites/<id>`

---

## [0.1.22] - 2026-06-07

### Added
- Repos-Tab: Stars ⭐, Forks 🍴 und Watchers 👁 je Repo als kompakte Statistik-Zeile im Übersichts-Card
- Telegram: Benachrichtigung wenn sich Stars, Forks oder Watchers eines eigenen Repos ändern (mit Vorher/Nachher und Differenz)

---

## [0.1.21] - 2026-06-07

### Fixed
- Workflow-Run löschen löste danach eine Telegram-Benachrichtigung aus: `_known_run_conclusions` wurde nach dem Löschen geleert, wodurch der Run beim nächsten Poll als "neu" galt; Eintrag bleibt jetzt erhalten

---

## [0.1.20] - 2026-06-07

### Added
- CI/Actions: 🗑 Löschen-Button für abgeschlossene Workflow-Runs — entfernt den Run direkt auf GitHub und aus dem lokalen Cache ohne neuen Poll

---

## [0.1.19] - 2026-06-07

### Changed
- Repos-Tab: Repo-Name ist jetzt als Link sichtbar (accent-Farbe + Extern-Pfeil-Icon) und öffnet GitHub im neuen Tab

---

## [0.1.18] - 2026-06-07

### Added
- Neuer **Repos**-Tab als Startseite: zeigt alle eigenen Repos mit offenen PRs, Issues und letztem CI-Run auf einen Blick; Klick auf eine Zahl öffnet den zugehörigen Detail-Tab
- PR-Kachel öffnet jetzt den Pull-Requests-Tab (statt Repos-Tab)

---

## [0.1.17] - 2026-06-07

### Changed
- "Neu"-Indikator bei Releases: roter Punkt → grüner pulsierender Punkt (passt besser zu "neue gute Neuigkeit")

---

## [0.1.16] - 2026-06-07

### Fixed
- "Als gelesen markieren" hat fälschlicherweise die gesamte Seen-Liste geleert → beim nächsten Poll galten alle Releases wieder als neu und Telegram feuerte erneut; jetzt werden alle aktuell sichtbaren Releases zur Seen-Liste hinzugefügt (nicht gelöscht) — nur echte neue Releases lösen künftig Telegram aus

---

## [0.1.15] - 2026-06-07

### Fixed
- Poll-Intervall wurde intern auf mindestens 60 Sekunden erzwungen (`max(60, ...)`) — der konfigurierte Wert wurde ignoriert; Minimum jetzt 10 Sekunden

---

## [0.1.14] - 2026-06-07

### Changed
- CI/Actions: Workflow-Runs werden jetzt bis zu 25 statt nur 10 geladen

---

## [0.1.13] - 2026-06-07

### Added
- Stat-Kacheln blinken bei neuen Einträgen: PRs (grün), Issues (gelb), Releases (lila) — Blinken stoppt sobald der zugehörige Tab geöffnet wird; Workflows-Kachel blinkt nicht

---

## [0.1.12] - 2026-06-07

### Fixed
- API Rate-Limit Tooltip: Text war hardcodiert auf Deutsch — jetzt lokalisiert (DE/EN)

---

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
