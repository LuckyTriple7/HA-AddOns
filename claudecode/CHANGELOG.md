# Changelog

## [1.0.13] - 2026-05-26

### Fixed
- `claude update` wird abgefangen und via npm ausgeführt (verhindert Fehler auf read-only Docker-Layern)

## [1.0.12] - 2026-05-25

### Changed
- Konfigurationsblock beim Start ins LOG: alle gesetzten Optionen auf einen Blick
- Update-Checker loggt Start und jeden stündlichen Check-Vorgang
- Memory-Backup loggt Start und jeden geplanten Backup-Lauf
- Alle Options-Reads zusammengeführt (saubere Struktur in run.sh)

## [1.0.11] - 2026-05-25

### Fix
- Background-Update-Checker läuft jetzt nur noch wenn `auto_update_claude` aktiviert ist; war bisher immer aktiv und schickte HA-Benachrichtigungen auch bei deaktiviertem Auto-Update

## [1.0.10] - 2026-05-25

### Neu
- Option `export_memory_interval`: zeitgesteuerter Memory-Export im Hintergrund (in Minuten). 0 = nur beim Start, Standard: 60 (stündlich). Nur aktiv wenn `export_memory` aktiviert ist.

## [1.0.9] - 2026-05-25

### Neu
- Option `export_memory`: kopiert beim Add-on-Start Memory-Dateien, Memory-Index und eigene Befehle in den Add-on-Konfigurationsordner (`/config/memory/` und `/config/commands/`). Standard: deaktiviert.

## [1.0.8] - 2026-05-24

### Neu
- Option `claude_autostart`: Claude Code startet automatisch beim Öffnen des Terminals; nach dem Beenden öffnet sich eine normale Bash-Shell

## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.6] - 2026-05-22

### Changed
- Rebuild für Claude Code 2.1.148


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.5] - 2026-05-21

### Changed
- Rebuild für Claude Code 2.1.146


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.6] - 2026-05-22

### Changed
- Rebuild für Claude Code 2.1.148


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.4] - 2026-05-20

### Changed
- Rebuild für Claude Code 2.1.145


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.6] - 2026-05-22

### Changed
- Rebuild für Claude Code 2.1.148


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.5] - 2026-05-21

### Changed
- Rebuild für Claude Code 2.1.146


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.6] - 2026-05-22

### Changed
- Rebuild für Claude Code 2.1.148


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.3] - 2026-05-19

### Changed
- Rebuild für Claude Code 2.1.144


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.6] - 2026-05-22

### Changed
- Rebuild für Claude Code 2.1.148


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.5] - 2026-05-21

### Changed
- Rebuild für Claude Code 2.1.146


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.6] - 2026-05-22

### Changed
- Rebuild für Claude Code 2.1.148


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.4] - 2026-05-20

### Changed
- Rebuild für Claude Code 2.1.145


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.6] - 2026-05-22

### Changed
- Rebuild für Claude Code 2.1.148


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.5] - 2026-05-21

### Changed
- Rebuild für Claude Code 2.1.146


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.6] - 2026-05-22

### Changed
- Rebuild für Claude Code 2.1.148


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.2] - 2026-05-15

### Changed
- Rebuild für Claude Code 2.1.143

## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.6] - 2026-05-22

### Changed
- Rebuild für Claude Code 2.1.148


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.5] - 2026-05-21

### Changed
- Rebuild für Claude Code 2.1.146


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.6] - 2026-05-22

### Changed
- Rebuild für Claude Code 2.1.148


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.4] - 2026-05-20

### Changed
- Rebuild für Claude Code 2.1.145


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.6] - 2026-05-22

### Changed
- Rebuild für Claude Code 2.1.148


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.5] - 2026-05-21

### Changed
- Rebuild für Claude Code 2.1.146


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.6] - 2026-05-22

### Changed
- Rebuild für Claude Code 2.1.148


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.3] - 2026-05-19

### Changed
- Rebuild für Claude Code 2.1.144


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.6] - 2026-05-22

### Changed
- Rebuild für Claude Code 2.1.148


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.5] - 2026-05-21

### Changed
- Rebuild für Claude Code 2.1.146


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.6] - 2026-05-22

### Changed
- Rebuild für Claude Code 2.1.148


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.4] - 2026-05-20

### Changed
- Rebuild für Claude Code 2.1.145


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.6] - 2026-05-22

### Changed
- Rebuild für Claude Code 2.1.148


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.5] - 2026-05-21

### Changed
- Rebuild für Claude Code 2.1.146


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.6] - 2026-05-22

### Changed
- Rebuild für Claude Code 2.1.148


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.1] - 2026-05-15

### Fixed
- Deprecated `build.yaml` entfernt — Build-Parameter direkt ins Dockerfile verschoben
- Deutsche Übersetzung hinzugefügt

## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.6] - 2026-05-22

### Changed
- Rebuild für Claude Code 2.1.148


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.5] - 2026-05-21

### Changed
- Rebuild für Claude Code 2.1.146


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.6] - 2026-05-22

### Changed
- Rebuild für Claude Code 2.1.148


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.4] - 2026-05-20

### Changed
- Rebuild für Claude Code 2.1.145


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.6] - 2026-05-22

### Changed
- Rebuild für Claude Code 2.1.148


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.5] - 2026-05-21

### Changed
- Rebuild für Claude Code 2.1.146


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.6] - 2026-05-22

### Changed
- Rebuild für Claude Code 2.1.148


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.3] - 2026-05-19

### Changed
- Rebuild für Claude Code 2.1.144


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.6] - 2026-05-22

### Changed
- Rebuild für Claude Code 2.1.148


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.5] - 2026-05-21

### Changed
- Rebuild für Claude Code 2.1.146


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.6] - 2026-05-22

### Changed
- Rebuild für Claude Code 2.1.148


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.4] - 2026-05-20

### Changed
- Rebuild für Claude Code 2.1.145


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.6] - 2026-05-22

### Changed
- Rebuild für Claude Code 2.1.148


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.5] - 2026-05-21

### Changed
- Rebuild für Claude Code 2.1.146


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.6] - 2026-05-22

### Changed
- Rebuild für Claude Code 2.1.148


## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150


## [1.0.0] - 2026-05-15

Forked from [apbb2/robsonfelix-hass-addons](https://github.com/apbb2/robsonfelix-hass-addons).

### Fixed
- Playwright MCP: socat forwards port 80 → Playwright Browser add-on port 9222,
  so the CDP endpoint is reliably reachable without manual workarounds.
