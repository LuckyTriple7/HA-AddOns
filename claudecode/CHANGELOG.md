# Changelog

## [1.0.39] - 2026-06-21

### Changed
- Rebuild für Claude Code 2.1.185


## [1.0.38] - 2026-06-20

### Changed
- Rebuild für Claude Code 2.1.183


## [1.0.37] - 2026-06-16

### Changed
- Rebuild für Claude Code 2.1.178


## [1.0.36] - 2026-06-13

### Changed
- Rebuild für Claude Code 2.1.177


## [1.0.35] - 2026-06-12

### Changed
- Rebuild für Claude Code 2.1.175


## [1.0.34] - 2026-06-11

### Changed
- Rebuild für Claude Code 2.1.173


## [1.0.33] - 2026-06-10

### Added
- Neues Modell `claude-fable-5` in der Modellauswahl (Anthropics leistungsstärkstes Modell, bis 22.06.2026 ohne Credit-Verbrauch auf bezahlten Plänen)

### Changed
- Doku: veraltete Modellbezeichnung `claude-opus-4-7` durch `claude-opus-4-8` ersetzt


## [1.0.32] - 2026-06-10

### Changed
- Rebuild für Claude Code 2.1.170


## [1.0.31] - 2026-06-09

### Changed
- Rebuild für Claude Code 2.1.169


## [1.0.30.1] - 2026-06-08

Bump python from 3.13-alpine3.21 to 3.14-alpine3.21


## [1.0.30] - 2026-06-07

### Changed
- Rebuild für Claude Code 2.1.168


## [1.0.29] - 2026-06-06

### Fixed
- `notify_on_update`, `auto_update_claude`, `enable_mcp`, `session_persistence`: jq `//`-Operator behandelte `false` als falsy und lieferte immer den Standardwert `true` — Option auf `false` hatte keinen Effekt

## [1.0.28] - 2026-06-06

### Changed
- Rebuild für Claude Code 2.1.167


## [1.0.27] - 2026-06-05

### Changed
- Rebuild für Claude Code 2.1.165


## [1.0.26] - 2026-06-05

### Changed
- Rebuild für Claude Code 2.1.163


## [1.0.25] - 2026-06-04
- Log-Ausgaben mit Datum und Uhrzeit: `[INFO] [YYYY-MM-DD HH:MM:SS] Nachricht`

## [1.0.24] - 2026-06-04

### Added
- Neue Option `notify_on_update` (Standard: aktiviert): HA-Persistent-Notification bei Update kann deaktiviert werden, ohne den Update-Check selbst abzuschalten.

## [1.0.23] - 2026-06-04

### Changed
- Rebuild für Claude Code 2.1.162

## [1.0.22] - 2026-06-03

### Changed
- Build: Image wird jetzt via GitHub Actions auf GHCR gebaut (ghcr.io/luckytriple7/claudecode)
- Build: Basis-Image auf python:3.13-alpine3.21 umgestellt, TARGETARCH statt BUILD_ARCH

## [1.0.21] - 2026-06-03

### Changed
- Rebuild für Claude Code 2.1.161

## [1.0.20] - 2026-06-02

### Changed
- Rebuild für Claude Code 2.1.160

## [1.0.19] - 2026-06-01

### Changed
- Rebuild für Claude Code 2.1.159

## [1.0.18] - 2026-05-30

### Changed
- Rebuild für Claude Code 2.1.158

## [1.0.17] - 2026-05-29

### Changed
- claude-opus-4-7 durch claude-opus-4-8 ersetzt

## [1.0.16] - 2026-05-29

### Changed
- Rebuild für Claude Code 2.1.156

## [1.0.15] - 2026-05-28

### Changed
- Rebuild für Claude Code 2.1.153

## [1.0.14] - 2026-05-27

### Changed
- Rebuild für Claude Code 2.1.152

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

### Fixed
- Background-Update-Checker läuft jetzt nur noch wenn `auto_update_claude` aktiviert ist; war bisher immer aktiv und schickte HA-Benachrichtigungen auch bei deaktiviertem Auto-Update

## [1.0.10] - 2026-05-25

### Added
- Option `export_memory_interval`: zeitgesteuerter Memory-Export im Hintergrund (in Minuten). 0 = nur beim Start, Standard: 60 (stündlich). Nur aktiv wenn `export_memory` aktiviert ist.

## [1.0.9] - 2026-05-25

### Added
- Option `export_memory`: kopiert beim Add-on-Start Memory-Dateien, Memory-Index und eigene Befehle in den Add-on-Konfigurationsordner (`/config/memory/` und `/config/commands/`). Standard: deaktiviert.

## [1.0.8] - 2026-05-24

### Added
- Option `claude_autostart`: Claude Code startet automatisch beim Öffnen des Terminals; nach dem Beenden öffnet sich eine normale Bash-Shell

## [1.0.7] - 2026-05-23

### Changed
- Rebuild für Claude Code 2.1.150

## [1.0.6] - 2026-05-22

### Changed
- Rebuild für Claude Code 2.1.148

## [1.0.5] - 2026-05-21

### Changed
- Rebuild für Claude Code 2.1.146

## [1.0.4] - 2026-05-20

### Changed
- Rebuild für Claude Code 2.1.145

## [1.0.3] - 2026-05-19

### Changed
- Rebuild für Claude Code 2.1.144

## [1.0.2] - 2026-05-15

### Changed
- Rebuild für Claude Code 2.1.143

## [1.0.1] - 2026-05-15

### Fixed
- Deprecated `build.yaml` entfernt — Build-Parameter direkt ins Dockerfile verschoben
- Deutsche Übersetzung hinzugefügt

## [1.0.0] - 2026-05-15

Forked from [apbb2/robsonfelix-hass-addons](https://github.com/apbb2/robsonfelix-hass-addons).

### Fixed
- Playwright MCP: socat forwards port 80 → Playwright Browser add-on port 9222,
  so the CDP endpoint is reliably reachable without manual workarounds.
