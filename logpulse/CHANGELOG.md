# Changelog

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
