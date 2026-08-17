# Changelog

## [1.0.5] - 2026-08-17

- Doku: Firefox und die noVNC-Kernbibliothek stehen unter der MPL-2.0, das Add-on gab bisher keine Lizenz an. Neue `LICENSE.md` nennt die mitgelieferten Bestandteile, ihre Lizenzen und Bezugsquellen, hält fest, dass das offizielle Mozilla-Build unverändert ausgeliefert wird, und weist auf die Markenrichtlinie hin

## [1.0.4.1] - 2026-08-17

chore(deps): Bump jlesage/baseimage-gui from debian-12-v4.13.0 to debian-12-v4.13.1 in /firefox


## [1.0.4] - 2026-07-21

### Geändert
- Rebuild für Firefox ESR 140.13.0esr


## [1.0.3.2] - 2026-07-13

chore(deps): bump jlesage/baseimage-gui from debian-12-v4.12.5 to debian-12-v4.12.6 in /firefox


## [1.0.3.1] - 2026-06-22

build(deps): Bump jlesage/baseimage-gui from debian-12-v4.12.4 to debian-12-v4.12.5 in /firefox


## [1.0.3] - 2026-06-16

### Geändert
- Rebuild für Firefox ESR 140.12.0esr


## [1.0.2.1] - 2026-06-09

chore(deps): Bump jlesage/baseimage-gui from debian-12-v4.12.1 to debian-12-v4.12.4 in /firefox


## [1.0.2] - 2026-05-19

### Geändert
- Rebuild für Firefox ESR 140.11.0esr


## [1.0.1] - 2026-05-17

### Geändert
- Automatischer Firefox-Updater deaktiviert (`policies.json`) — Updates kommen ausschließlich über das Docker-Image

## [1.0.2] - 2026-05-19

### Geändert
- Rebuild für Firefox ESR 140.11.0esr


## [1.0.0] - 2026-05-16

### Erstveröffentlichung

- Firefox ESR direkt in der HA-Seitenleiste via noVNC (kein externer VNC-Client nötig)
- Deutsche Sprachversion (direkt von Mozilla geladen)
- Eigenes Docker-Image auf Basis von `jlesage/baseimage-gui:debian-12` — VNC, noVNC und Window Manager vom Base-Image übernommen
- Firefox direkt von Mozilla geladen (immer aktuelle ESR-Version)
- Persistentes Firefox-Profil in `/data/profile` — überdauert Neustarts und Updates
- Downloads werden in `/share/firefox` gespeichert
- Nur amd64
- Konfigurationsoptionen: `DISPLAY_WIDTH`, `DISPLAY_HEIGHT`, `DARK_MODE`, `VNC_PASSWORD`, `KEEP_APP_RUNNING`, `TZ`, `FF_OPEN_URL`, `FF_KIOSK`, `FF_CUSTOM_ARGS`, `memory_limit_mb`
- Software-Rendering aktiviert (`gfx.webrender.software`, `LIBGL_ALWAYS_SOFTWARE`) — kein GPU nötig
