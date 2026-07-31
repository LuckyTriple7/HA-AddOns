# Changelog

## [0.6.5] - 2026-07-31
- map: `addon_config` → `app_config` (Home-Assistant-Supervisor hat `addon_config` seit 2026.07 als Legacy-Name markiert, neuer Name ist `app_config`).

## [0.6.4] - 2026-07-09

### Fixed
- CodeQL-Funde behoben: `/set-lang/<lang>` setzte den Sprach-Cookie mit dem
  Pfad-Parameter statt einem geprüften Literal (Allowlist war zwar schon da,
  jetzt auch für statische Analyse eindeutig sichtbar). Im Frontend konnte ein
  Log-Level mit `"` darin aus dem `class="..."`-Attribut ausbrechen
  (`levelClass()` jetzt mit fester Whitelist statt freier String-Konkatenation)
  und `f.source`/`f.levels` bei gespeicherten Filtern landeten ungeescaped im
  DOM — beide jetzt über `escapeHtml()`.

## [0.6.3] - 2026-07-09

### Changed
- Startphase auf `startup: system` vorgezogen — LogPulse startet jetzt vor
  HA Core (wie Datenbank-Add-ons) und erfasst Live-Logs schon während des
  Core-Starts

## [0.6.2] - 2026-07-09

### Fixed
- Konsolen-Toolbar (Leeren, Pausieren, Auto-Scroll) verschwand beim Scrollen der
  Seite — jetzt sticky unter der Filterleiste (Live-Tab) bzw. am oberen Rand
  (Konsole-Tab). Filterleisten-Höhe wird per ResizeObserver verfolgt, da Chips
  je nach Fensterbreite umbrechen
- Scroll-Chaining unterbunden (`overscroll-behavior: contain`): Wer im Log-Fenster
  am Anfang/Ende weiterscrollt, scrollt nicht mehr versehentlich die ganze Seite

## [0.6.1] - 2026-07-09

### Fixed
- Add-on beendete sich bei jedem Stop/Update mit Exit-Code 137 (SIGKILL statt
  sauberem Stop). Ursache: `Dockerfile` basiert auf reinem `debian:bookworm-slim`
  ohne eigenes Init-System, `run.sh` macht den Flask-Prozess per `exec` zu PID 1 —
  ohne eigenen Signal-Handler ignoriert der Kernel bei PID 1 unbehandelte Signale
  wie SIGTERM (Linux-Sonderfall), der Supervisor musste nach Timeout hart killen.
  `init: false` → `init: true` in `config.yaml` (Supervisor stellt jetzt ein
  Mini-Init als echte PID 1) plus eigener `SIGTERM`-Handler in `app.py`
  (`os._exit(0)` — alle Hintergrund-Threads sind daemon, kein Cleanup nötig).

## [0.6.0] - 2026-07-09

- Neue Option `min_level` (DEBUG/INFO/WARNING/ERROR): nur Einträge ab diesem Level werden noch gespeichert, Rest wird direkt beim Ingest verworfen. Reduziert DB-Wachstum und Last bei hohem Log-Volumen, Standard bleibt DEBUG (unverändertes Verhalten)
- Neuer Schalter im Header: Log-Erfassung komplett pausieren/fortsetzen. Bei Pause wird journald gar nicht erst geöffnet — kein Lesen, kein Klassifizieren, keine DB-Writes, spart die volle Ingest-Last, solange niemand die Logs braucht. Zustand übersteht Neustarts (`/data/ingest_state.json`)
- CPU-/RAM-Auslastung von LogPulse selbst jetzt in der Summary-Bar sichtbar (wie bei SysWatch), via `/proc/self` — kein zusätzlicher docker_api-Zugriff nötig

## [0.5.1] - 2026-07-09

- Fix: hohe, mit der Laufzeit steigende CPU-Last. Ursache: die FTS5-Tabelle `log_fts` samt Insert-/Delete-Trigger aus v0.1.0 lief unbemerkt weiter, obwohl die Suche seit v0.3.4 nur noch `LIKE` nutzt — jede Log-Zeile wurde zusätzlich in FTS5-Segmente geschrieben, deren Merge-Kosten mit der DB-Größe wuchsen. Tabelle + Trigger entfernt, bestehende Datenbanken werden beim Start automatisch migriert (Trigger/Tabelle gedroppt, `VACUUM` + `wal_checkpoint(TRUNCATE)` geben den belegten Platz sofort zurück)

## [0.5.0] - 2026-07-08

- Offline-Banner ergänzt (wie TUIWatch/SysWatch): nach 3 gescheiterten Polls oder `navigator.onLine=false` erscheint Verbindungs-Overlay mit Reload-Button
- Session-Timeout gefixt: API-Routen gaben bei abgelaufener Session einen Redirect zurück statt 401 — `fetch()` folgt Redirects transparent, `res.json()` scheiterte dann still auf der Login-HTML-Seite, UI blieb scheinbar eingefroren. API-Routen liefern jetzt 401, Frontend leitet bei 401 aktiv zu `/login` um
- Filterleiste + Quellen-Tabs im Live-Tab sind jetzt sticky (bleiben beim Scrollen der Log-Liste oben stehen)

## [0.4.2] - 2026-07-08

- Neue App-Icons (icon.png, icon-192.png, icon-512.png)

## [0.4.1] - 2026-07-08

- Fix: Level-Badge (`[WARNING]`) brach in schmalen Panels mitten im Wort um (`WARNIN` / `G]`) — `word-break:break-all` vom Log-Container griff auf Zeitstempel/Level/Quelle statt nur auf die Nachricht. Jetzt `white-space:nowrap` auf Zeitstempel-, Level- und Quellen-Spalte, nur die Nachricht selbst darf umbrechen

## [0.4.0] - 2026-07-08

- Root-Fix statt weiterer Einzel-Regex: journald-PRIORITY bei Docker-Containern ist nur ein Stream-Signal (stdout=6/stderr=3), kein echter Schweregrad — viele Tools (Ring-MQTT, u.a.) loggen normale Infos komplett über stderr. Container-Zeilen ohne erkennbaren Text-Marker (Crowdsec/lws/Uptime-Kuma-Muster etc.) fallen jetzt auf INFO statt auf den rohen stderr-Wert. Echte System-/Host-Journal-Einträge (`source=system`) nutzen PRIORITY weiterhin, da dort verlässlich

## [0.3.4] - 2026-07-08

- Fix: Suche fand nichts bei Eingabe eines Addon-Namens (z.B. "Cloudflared") — FTS5 durchsuchte nur den Nachrichtentext, nicht Container-/Add-on-Namen, und `MATCH` lässt sich technisch nicht mit `OR` kombinieren. Umgestellt auf `LIKE` über Nachricht + Container + Add-on-Name + Identifier

## [0.3.3] - 2026-07-08

- Fix: Uptime Kuma-Format (`... [DOMAIN_EXPIRY] WARN: msg`) wurde als ERROR gewertet — generisches Muster ergänzt, das ein LEVEL-Wort direkt vor einem Doppelpunkt erkennt
- Fix: DB-Größe nach „Datenbank leeren" sank nicht spürbar — `VACUUM` schreibt im WAL-Modus zunächst nur in die `-wal`-Datei, Hauptdatei blieb unverändert. Expliziter `PRAGMA wal_checkpoint(TRUNCATE)` danach ergänzt (getestet: 10,8 MB → 12 KB)

## [0.3.2] - 2026-07-08

- Fix: libwebsockets-Format (Collabora Online, Claude Code — `[2026/07/08 17:00:29:1164] N: ...`) wurde ebenfalls komplett als ERROR gewertet. Neues Muster erkennt den Ein-Buchstaben-Level nach dem Zeitstempel (E/W/N/I/D/P), N(otice)/I(nfo)/D(ebug) zählen jetzt korrekt nicht als Fehler

## [0.3.1] - 2026-07-08

- Fix: Go-Tools wie Crowdsec (Logrus-Format `level=info ...`) wurden komplett als ERROR gewertet — keins der bisherigen Level-Muster passte, also griff der journald-PRIORITY-Fallback (stderr → ERROR), unabhängig vom echten Level im Text. Neues Muster erkennt `level=debug/info/warn/error/fatal/panic` überall in der Zeile

## [0.3.0] - 2026-07-08

- Klick auf DB-Größe-Chip fragt nach ("Datenbank komplett leeren?" Ja/Nein) und löscht bei Bestätigung alle Log-Einträge (`DELETE` + `VACUUM`, sofort wieder Platz auf der Disk)

## [0.2.3] - 2026-07-08

- Fix: „Einträge"-Chip hing bei 1000 fest — Summary-Bar nutzte `/api/logs?limit=1000` und zählte die zurückgegebene Liste clientseitig. Neuer Endpoint `/api/stats` liefert echte COUNT(*)-Werte (Total + Warnungen/Fehler), ungedeckelt
- Fix: DB-Größe-Chip nicht bündig mit den anderen Chips (Text brach bei langen Werten um, Chip wurde höher). `white-space:nowrap` + `justify-content:center` auf `.stat-chip`

## [0.2.2] - 2026-07-08

- Fix: `/api/logs` warf bei Volltextsuche `sqlite3.OperationalError: ambiguous column name: message` — `log_fts` und `log_entries` haben beide eine `message`-Spalte, jetzt eindeutig mit `log_entries.message`/`log_entries.id` qualifiziert

## [0.2.1] - 2026-07-08

- Fix: Browser-Tab fror ein, wenn man das HA-Ingress-Panel verließ. HA hält Ingress-Panels beim Wechsel oft nur "hidden" statt sie zu zerstören — Long-Poll (`/api/wait`) lief im Hintergrund ohne Backoff weiter und konnte bei Verbindungsfehlern in eine ungebremste Dauerschleife laufen. Jetzt: alle Polls (Live-Tail, Konsole, DB-Größe, Summary) pausieren bei `document.hidden`, garantierter Backoff (3s) bei Fehlern, DOM-Zeilen in Live/Konsole auf 500 gedeckelt

## [0.2.0] - 2026-07-08

- Quellen-Tab: Klick auf eine Zeile filtert Live-Tab auf genau diesen Container (Chip mit ✕ zum Zurücksetzen)
- DB-Größe (inkl. WAL/SHM) in Summary-Bar und Quellen-Tab-Header, mit Aufbewahrungsdauer

## [0.1.0] - 2026-07-08

- Erste Version: journald-Ingest (HA Core, Supervisor, alle Addon-Container), SQLite-Persistenz mit Volltextsuche (FTS5), Retention (Tage + Größenlimit), Web-UI im GitPulse-Look (Live-Tab, Quellen-Tab, gespeicherte Filter, Konsole)
