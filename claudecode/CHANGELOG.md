# Changelog

## [1.1.17] - 2026-07-26

### Changed
- Modellauswahl: `claude-opus-5` ersetzt `claude-opus-4-8`, `claude-sonnet-4-6` entfernt (Standard bleibt `claude-sonnet-5`)


## [1.1.16] - 2026-07-25

### Changed
- Rebuild für Claude Code 2.1.220


## [1.1.15] - 2026-07-23

### Changed
- Rebuild für Claude Code 2.1.218


## [1.1.14] - 2026-07-21

### Changed
- Rebuild für Claude Code 2.1.216


## [1.1.13] - 2026-07-19

### Fixed
- Ungültige `Glob(...)`/`Grep(...)` Permission-Regeln entfernt (Warnung "not matched by file permission checks"); `Read(...)` deckt alle Datei-Lese-Tools bereits ab
- Bestehende Installationen: alte fehlerhafte Regeln werden beim Start aus persistierter settings.json bereinigt


## [1.1.12] - 2026-07-19

### Changed
- Rebuild für Claude Code 2.1.215


## [1.1.11] - 2026-07-16

### Changed
- Rebuild für Claude Code 2.1.211


## [1.1.10] - 2026-07-15

### Changed
- Rebuild für Claude Code 2.1.210


## [1.1.9] - 2026-07-14

### Changed
- Rebuild für Claude Code 2.1.209


## [1.1.8] - 2026-07-11

### Changed
- Rebuild für Claude Code 2.1.207


## [1.1.7] - 2026-07-10

### Changed
- Rebuild für Claude Code 2.1.206


## [1.1.6] - 2026-07-09

### Changed
- Doku (DE/EN) und Options-Beschreibungen: Hinweis auf tmux-Copy-Mode-Falle im `tmux`-Scroll-Modus — erstes Scrollen öffnet Copy-Mode, Eingabe wirkt blockiert, `q` verlässt ihn

## [1.1.5] - 2026-07-09

### Fixed
- Web-Terminal-Scrollback: Die tmux-Statuszeile ließ tmux in einer Scroll-Region (DECSTBM) scrollen, wodurch gescrollte Zeilen nie das Browser-Scrollback erreichten — nur wenige Zeilen waren scrollbar (#162)

### Added
- Neue Option `tmux_scroll_mode` (`browser`|`tmux`, Standard: `browser`): `browser` = natives Browser-Scrollen, Touch (iPad) und normales Kopieren/Einfügen; `tmux` = Mausrad scrollt tmux-Historie, überlebt Browser-Reloads

## [1.1.4] - 2026-07-09

### Changed
- Rebuild für Claude Code 2.1.205


## [1.1.3] - 2026-07-08

### Changed
- Rebuild für Claude Code 2.1.204


## [1.1.2] - 2026-07-07

### Changed
- Rebuild für Claude Code 2.1.202


## [1.1.1] - 2026-07-04

### Changed
- Rebuild für Claude Code 2.1.201


## [1.1.0] - 2026-07-03

### Added
- Optionaler "Caveman"-Skill für Claude Code (`enable_caveman_skill`, Standard: deaktiviert) — knappe, technisch präzise Antworten ohne Füllwörter. Wird bei aktivierter Option bei jedem Start nach `/root/.claude/skills/caveman` synchronisiert.


## [1.0.47] - 2026-07-02

### Changed
- Rebuild für Claude Code 2.1.198


## [1.0.46] - 2026-07-01

### Added
- Neues Modell `claude-sonnet-5` zur Auswahl hinzugefügt und als Standard gesetzt


## [1.0.45] - 2026-07-01

### Changed
- Rebuild für Claude Code 2.1.197


## [1.0.44] - 2026-06-30

### Changed
- Rebuild für Claude Code 2.1.196


## [1.0.43] - 2026-06-27

### Changed
- Rebuild für Claude Code 2.1.195


## [1.0.42] - 2026-06-26

### Changed
- Rebuild für Claude Code 2.1.193


## [1.0.41] - 2026-06-25

Update Claude Code 2.1.191 (Add-on v1.0.40)


## [1.0.40] - 2026-06-25

### Changed
- Rebuild für Claude Code 2.1.191


## [1.0.39] - 2026-06-22

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
