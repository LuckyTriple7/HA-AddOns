# Changelog — Nextcloud

## 0.0.8
- Timeout erhöht: 10 → 30 Minuten (erster Start lädt ~100 MB Nextcloud herunter)

## 0.0.7
- occ-Pfad dynamisch per find_occ() ermittelt (mehrere Kandidaten + breite Suche)
- Warte-Schleife zeigt alle 30s was in /config und /app liegt

## 0.0.6
- Diagnose-Output in Warte-Schleife (alle 30s Verzeichnisinhalt)

## 0.0.5
- Verbose Logging für occ maintenance:install (Fehlerausgabe nicht mehr unterdrückt)

## 0.0.4
- Fix: Warte-Schleife für Nextcloud-Dateien — linuxserver kopiert diese asynchron nach dem Start

## 0.0.3
- Fix: `s6-overlay-suexec` Fehler — occ läuft jetzt als root mit `--allow-root`
- Fix: `exec /init` entfernt — s6-overlay läuft bereits als PID 1, run.sh ist CMD-Callback
- Fix: Warte-Schleife entfernt — Nextcloud-Dateien sind bereits bereit wenn run.sh startet

## 0.0.2
- MariaDB Discovery Schalter (default: aus → immer SQLite)
- Logo hinzugefügt

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
