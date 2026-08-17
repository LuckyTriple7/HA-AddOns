# Changelog — phpMyAdmin Maria DB 2

## [1.0.6] - 2026-08-17

- Doku: `org.opencontainers.image.licenses` im Dockerfile stand auf MIT, obwohl das Image phpMyAdmin unter der GPL-2.0 enthält — auf `GPL-2.0-only AND MIT` korrigiert

## [1.0.5] - 2026-08-17

- Doku: phpMyAdmin steht unter der GPL-2.0, das Add-on gab bisher keine Lizenz an. Neue `LICENSE.md` nennt Lizenz und Bezugsquelle des Quelltextes und grenzt die eigenen MIT-Dateien davon ab

## [1.0.4] - 2026-06-04

### Fixed
- YAML-Fehler in Translations behoben (--- Separator entfernt)

## [1.0.3] - 2026-06-04

### Fixed
- phpMyAdmin-Datenbank-Init entfernt — verhinderte Start wenn User keine CREATE-Rechte hat (Datenbank ist optional)

## [1.0.2] - 2026-06-04

### Fixed
- Executable-Bit auf s6-overlay Scripts gesetzt (Permission denied beim Start behoben)

## [1.0.1] - 2026-06-04

### Fixed
- Versions-Pins aus Dockerfile entfernt (Alpine-Pakete nicht mehr verfügbar)

## [1.0.0] - 2026-06-04

### Added
- Initiale Version basierend auf dem offiziellen phpMyAdmin Community Add-on
- Verbindung zu MariaDB 2 statt zur offiziellen MariaDB-Instanz
- Konfigurierbare Optionen: mysql_host, mysql_port, mysql_user, mysql_password
- Upload-Limit konfigurierbar (Standard: 64 MB)
