# Changelog — phpMyAdmin Maria DB 2

## [1.0.1] - 2026-06-04

### Fixed
- Versions-Pins aus Dockerfile entfernt (Alpine-Pakete nicht mehr verfügbar)

## [1.0.0] - 2026-06-04

### Added
- Initiale Version basierend auf dem offiziellen phpMyAdmin Community Add-on
- Verbindung zu MariaDB 2 statt zur offiziellen MariaDB-Instanz
- Konfigurierbare Optionen: mysql_host, mysql_port, mysql_user, mysql_password
- Upload-Limit konfigurierbar (Standard: 64 MB)
