# Changelog — HA SysWatch

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
