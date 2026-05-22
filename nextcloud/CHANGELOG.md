# Changelog — Nextcloud

## 0.0.1
- Erstveröffentlichung (Beta)
- Basiert auf `lscr.io/linuxserver/nextcloud:latest`
- MariaDB Autodiscovery: nutzt automatisch das HA MariaDB Add-on (Fallback: SQLite)
- SMB-Netzwerkspeicher: 3 konfigurierbare Slots
- Datenspeicherung im HA `addon_config`-Ordner
- Konfigurierbare PHP-Limits (memory, upload, post)
- Trusted Domains, Standard-Telefonregion, Thumbnails per Option
- Updates deaktivierbar via `disable_updates`
- AppArmor-Profil für CIFS-Mounts
