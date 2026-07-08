# Changelog

## [0.2.2] - 2026-07-08

- Fix: `/api/logs` warf bei Volltextsuche `sqlite3.OperationalError: ambiguous column name: message` — `log_fts` und `log_entries` haben beide eine `message`-Spalte, jetzt eindeutig mit `log_entries.message`/`log_entries.id` qualifiziert

## [0.2.1] - 2026-07-08

- Fix: Browser-Tab fror ein, wenn man das HA-Ingress-Panel verließ. HA hält Ingress-Panels beim Wechsel oft nur "hidden" statt sie zu zerstören — Long-Poll (`/api/wait`) lief im Hintergrund ohne Backoff weiter und konnte bei Verbindungsfehlern in eine ungebremste Dauerschleife laufen. Jetzt: alle Polls (Live-Tail, Konsole, DB-Größe, Summary) pausieren bei `document.hidden`, garantierter Backoff (3s) bei Fehlern, DOM-Zeilen in Live/Konsole auf 500 gedeckelt

## [0.2.0] - 2026-07-08

- Quellen-Tab: Klick auf eine Zeile filtert Live-Tab auf genau diesen Container (Chip mit ✕ zum Zurücksetzen)
- DB-Größe (inkl. WAL/SHM) in Summary-Bar und Quellen-Tab-Header, mit Aufbewahrungsdauer

## [0.1.0] - 2026-07-08

- Erste Version: journald-Ingest (HA Core, Supervisor, alle Addon-Container), SQLite-Persistenz mit Volltextsuche (FTS5), Retention (Tage + Größenlimit), Web-UI im GitPulse-Look (Live-Tab, Quellen-Tab, gespeicherte Filter, Konsole)
