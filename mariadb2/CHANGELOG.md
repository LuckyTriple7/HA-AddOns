# Changelog — MariaDB 2

## [0.0.7] - 2026-05-25
- Fix: Emoji/4-Byte-UTF8-Zeichen in Kalender-Einträgen führten zu Fehler bei Migration — `--skip-character-set-client-handshake` erzwingt utf8mb4 für alle Verbindungen
- Nextcloud-empfohlene InnoDB-Settings: `innodb-default-row-format=dynamic`, `transaction-isolation=READ-COMMITTED`

## [0.0.6] - 2026-05-25
- Fix: MariaDB hörte nicht auf TCP Port 3306 — Alpine Default-Config (skip-networking) wird jetzt im Dockerfile entfernt, --no-defaults verhindert Überschreiben der Port-Einstellung

## [0.0.5] - 2026-05-25
- `mysqld`/`mysql` durch `mariadbd`/`mariadb` ersetzt (keine Deprecated-Warnings mehr)
- MariaDB `[Note]`-Logs unterdrückt — LOG zeigt nur noch relevante `[INFO]`-Zeilen

## [0.0.4] - 2026-05-25
- Option `create_nextcloud_db` entfernt — Passwort wird direkt in den App-Optionen gesetzt, einfacher und übersichtlicher

## [0.0.3] - 2026-05-25
- Hostname wird beim Start im LOG ausgegeben (wird für Nextcloud-Migration benötigt)

## [0.0.2] - 2026-05-25
- Zugangsdaten werden zusätzlich in `addon_config/nextcloud_db_credentials.txt` gespeichert (im HA-Dateibrowser einsehbar)

## [0.0.1] - 2026-05-25
- Erste Version: unabhängige MariaDB-Instanz auf Port 3307, parallel zur offiziellen MariaDB-App betreibbar
- Konfigurierbare Datenbanken, Zugangsdaten und Berechtigungen (wie Original)
- Option `create_nextcloud_db`: legt automatisch Nextcloud-Datenbank mit Zufallspasswort an
