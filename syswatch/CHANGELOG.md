# Changelog — HA SysWatch

## [0.2.0] - 2026-06-01

### Fixed
- Browser-Timer feuerte gelegentlich bevor neue Daten bereit waren — cycle_s Buffer von 0.3s auf 1.0s erhöht

## [0.1.9] - 2026-06-01

### Added
- `translations/en.yaml` und `translations/de.yaml` mit Beschreibungen aller Optionen (erscheinen jetzt in der HA Add-on UI)
- README.md und DOCS.md mit Performance-Tuning-Tabelle, Erklärungen zu collect_interval/collect_workers/viewer_timeout

## [0.1.8] - 2026-06-01

### Changed
- Interval-Dropdown entfernt — Browser kalibriert sich automatisch auf `cycle_s` (Abfragezeit + Sleep + Buffer) aus der Stats-Response
- Header zeigt statisch "~5.5s" (tatsächlicher Zyklus) statt konfigurierbarem Dropdown
- Backend gibt `cycle_s` in Stats-Response zurück

## [0.1.7] - 2026-06-01

### Fixed
- Auto-Refresh funktionierte nicht (SSE wurde durch Flask-Buffering verzögert) — ersetzt durch Long-Polling: Browser hält /api/wait offen, Server antwortet sofort nach jeder abgeschlossenen Docker-Abfrage; kein Proxy/Buffering-Problem möglich

## [0.1.6] - 2026-06-01

### Changed
- `collect_workers` Maximum von 32 auf 64 erhöht

## [0.1.5] - 2026-06-01

### Changed
- `viewer_timeout` als konfigurierbare Add-on-Option (Standard: 180s, Min: 30s, Max: 1800s / 30min)

## [0.1.4] - 2026-06-01

### Added
- SSE (Server-Sent Events): Browser bekommt sofort nach jeder Docker-Abfrage ein Push-Event und fetcht neue Daten — kein festes Polling-Interval mehr nötig; Timer bleibt als Fallback
- `/api/viewer` Endpoint: Pause/Resume-Button sendet sofort Signal ans Backend (Logausgabe, sofortiger Modus-Wechsel ohne 30s Wartezeit)
- Farbiger Modus-Dot im Header (grün=aktiv, gelb=idle, rot=pausiert)
- Pause-Button zeigt jetzt klar gelben Rand + Pause-Icon bei manuellem Pause, gedimmten Rand wenn Backend im IDLE-Modus

### Fixed
- Pause-Button-Klick war visuell unsichtbar — CSS-Klassen-Ansatz statt opacity-Manipulation

## [0.1.3] - 2026-06-01

### Fixed
- Collector startete beim Add-on-Start sofort im IDLE-Modus (60s Pause zwischen Abfragen), weil `_viewer_last_seen = 0.0` → wird jetzt auf `time.time()` initialisiert, Startup gilt als "aktiv"
- Heartbeat konnte den Collector nicht aus dem IDLE-Sleep aufwecken → `threading.Event` ersetzt `time.sleep`, Heartbeat weckt sofort auf

## [0.1.2] - 2026-06-01

### Added
- Startup-Banner im Log: Version, collect_interval, collect_workers, session_hours, Docker-Socket-Pfade
- Collector-Log pro Zyklus: Anzahl Container, laufende Container, Worker, Abfragedauer
- Modus-Wechsel-Log: IDLE→AKTIV und AKTIV→IDLE mit Grund und konfigurierten Werten
- Heartbeat-Log bei Übergang IDLE→AKTIV (IP-Adresse des Browsers)
- Abmeldungs-Log (Logout)

## [0.1.1] - 2026-06-01

### Added
- Performance-Mode: Browser sendet alle 10s einen Heartbeat; kein Heartbeat seit 30s → Backend wechselt automatisch in Idle-Modus (2 Worker, 60s Interval)
- Pause-Button (⚡/⏸) im Header zum manuellen Pausieren der Datenerfassung
- Visibility API: Heartbeat stoppt automatisch wenn Tab nicht sichtbar, nimmt bei Rückkehr sofort wieder auf
- Zustand wird in localStorage gespeichert

## [0.1.0] - 2026-06-01

### Added
- Kill-Button (Totenkopf-Icon) pro Container — sendet SIGKILL, erfordert Passwortbestätigung
- `collect_interval` (Standard: 3s) und `collect_workers` (Standard: 16, Min: 4, Max: 32) als konfigurierbare Add-on-Optionen

### Changed
- `refresh_interval` aus den Add-on-Optionen entfernt — UI-Dropdown (Standard 5s) reicht
- Browser-Standard-Refresh-Intervall auf 5s gesetzt

## [0.0.9] - 2026-06-01

### Fixed
- Paralleles Abfragen erhöhte CPU-Last spürbar — MAX_WORKERS auf 16 begrenzt, COLLECT_INTERVAL auf 3s erhöht; Zyklus ~6s bei deutlich reduzierter Last

## [0.0.8] - 2026-06-01

### Fixed
- Daten aktualisierten sich nur alle 10–15s statt im eingestellten Intervall — alle Container-Abfragen laufen jetzt vollständig parallel (ein Thread pro Container statt max. 12), Collector-Interval von 5s auf 1s reduziert → Gesamtzyklus ~2s

## [0.0.7] - 2026-06-01

### Added
- SYS RAM Karte zeigt `used / total` als Sub-Label (z.B. `11.3 GiB / 31.1 GiB`), kein Hover mehr nötig

## [0.0.6] - 2026-06-01

### Added
- Light/Dark-Mode-Toggle (Mond/Sonne-Icon im Header, gespeichert in localStorage)
- Light Mode auf Login-Seite ebenfalls verfügbar
- Aktualisierungsintervall 1s hinzugefügt
- Logout-Button durch Icon ersetzt (Pfeil nach rechts), Refresh-Button als Icon

## [0.0.5] - 2026-06-01

### Fixed
- Sticky-Tabellenkopf überlagerte erste Zeile — grundlegende Ursache behoben: `overflow-x: auto` auf `.table-wrap` machte es zum Scroll-Container und brach `position: sticky`. Lösung: `body` scrollt nicht mehr, Inhalt scrollt in `#main-scroll` (`flex: 1; overflow-y: auto`), horizontaler Scroll in separatem `.table-scroll`-Wrapper, `<th>` nun `top: 0`

### Added
- Passwortbestätigung beim Container-Neustart: Modal fragt das Dashboard-Passwort ab, Server validiert vor Ausführung (HTTP 403 bei falschem Passwort)

## [0.0.4] - 2026-06-01

### Fixed
- Sticky-Tabellenkopf überlagerte erste Zeile — Header-Höhe wird jetzt dynamisch per JS berechnet (`--hdr-h` CSS-Variable) statt fest auf 44px gesetzt

### Added
- CPU-Takt aus `/proc/cpuinfo` (Ø GHz + Anzahl Kerne) als Sub-Label unter der SYS-CPU-Karte

## [0.0.3] - 2026-06-01

### Fixed
- Logs-Button funktionierte nicht — HTML-Attribut-Bug durch onclick mit JSON.stringify behoben (Event-Delegation via data-action/data-name)

### Added
- Zwei neue Summary-Karten: SYS CPU % und SYS RAM % (Systemauslastung des Hosts via /proc/stat und /proc/meminfo)

## [0.0.2] - 2026-06-01

### Fixed
- `full_access: true` durch `docker_api: true` ersetzt — mountet `/var/run/docker.sock` korrekt und zeigt Docker-Badge in der HA Add-on UI
- Docker-Socket-Suche über mehrere Pfade (`/var/run/docker.sock`, `/run/docker.sock`, `/host/...`)
- Supervisor API als Fallback wenn Docker-Socket nicht verfügbar (zeigt HA Add-ons)

## [0.0.1] - 2026-06-01

### Added
- Initial release
- Sortable table with CPU %, RAM %, NET I/O, DISK I/O, PIDs per container
- Real-time CPU sparkline history per container
- Summary cards: total containers, running, total CPU, total RAM
- Auto-refresh (5 / 10 / 30 / 60 seconds, configurable)
- Log viewer modal (last 200 lines with timestamps)
- Container restart action with confirmation dialog
- Password-protected login with brute-force lockout (5 attempts / 15 min block)
- Session management with configurable expiry
- DE / EN language support
- PWA support (installable, service worker, manifest)
- Mobile-responsive layout
- Dark theme
