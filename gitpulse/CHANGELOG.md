# Changelog

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
