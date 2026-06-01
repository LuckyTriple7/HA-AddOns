# Changelog — HA SysWatch

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
