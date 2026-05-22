# Changelog — Nextcloud

## 0.0.29
- MIME-Type-Migrationen automatisch ausführen (occ maintenance:repair --include-expensive)

## 0.0.28
- Wartungsfenster auf 1 Uhr UTC gesetzt (= 2-3 Uhr nachts DE)

## 0.0.27
- Standardsprache für neue Benutzer auf Deutsch gesetzt (default_language=de, default_locale=de_DE)

## 0.0.26
- SMB-Shares nach Erstinstall automatisch als Externer Speicher registrieren (sichtbar im Dateimanager)

## 0.0.25
- Fix: /config/data wird mit chown abc:abc angelegt — Web-Installer kann schreiben

## 0.0.24
- Komplette Architektur-Überarbeitung nach Vorbild alexbelgium/hassio-addons
- Kein CMD-Override mehr — kein Race Condition mit linuxservers s6-Init
- ha-config.sh läuft jetzt AM ENDE von linuxservers init-nextcloud-config (occ bereit, config.php existiert)
- 30-ha-init.sh als cont-init.d Script: SMB-Mounts + PHP-Limits (früh, als root)
- Kein chown /config/data — linuxserver setzt Rechte selbst ("Setting permissions")
- trusted_domains und alle occ-Config schreiben jetzt zuverlässig in die richtige config.php

## 0.0.23
- Fix: OCC_BIN auf /app/www/public/occ geändert — dessen __DIR__/config/ zeigt via Symlink auf /config/www/nextcloud/config/ (persistente config.php), identisch zum Webserver
- Fix: OC_CONFIG_PATH-Workaround entfernt (war wirkungslos, weil occ __DIR__-relativ sucht)
- trusted_domains und alle anderen occ-Konfigurationen schreiben jetzt in die richtige config.php

## 0.0.22
- Fix: Installations-Check liest config.php direkt (grep statt occ status) — 100% zuverlässig nach Web-Installer

## 0.0.21
- Fix: OC_CONFIG_PATH=/config/www/nextcloud/config/ gesetzt — occ und Webserver nutzen jetzt garantiert dieselbe config.php (Symlink-Ansatz entfernt)

## 0.0.20
- Redesign: admin_user/admin_password entfernt — Ersteinrichtung über Web-Installer
- Fix: /app/www/src/config als Symlink auf /config/www/nextcloud/config (occ + Webserver nutzen dieselbe config.php)
- Fix: /config/data wird früh mit korrekten Rechten angelegt (Web-Installer kann schreiben)
- Neu: run.sh wartet nach Web-Install und wendet dann automatisch Konfiguration an

## 0.0.19
- Fix: /app/www/src/config als Symlink auf /config/www/nextcloud/config — occ und Webserver nutzen jetzt dieselbe config.php

## 0.0.18
- Fix: set -e entfernt (verhinderte frühen Scriptabbruch bei rm-Fehlern)
- Fix: alle rm/mkdir mit || true abgesichert
- Diagnose: Symlink-Struktur, config.php-Pfad und Inhalt nach Install im Log

## 0.0.17
- Fix: config.php aus allen möglichen Pfaden löschen (/app/www/public/, /app/www/src/, /config/www/nextcloud/)

## 0.0.16
- Fix: /config/data vor Installation mit PUID/PGID anlegen (Webserver-User kann schreiben)
- Fix: config.php vor Neuinstallation löschen (sauberer Reset)
- Fix: maintenance:install Exit-Code prüfen — bei Fehler klarer FAIL-Log statt stilles Weitermachen

## 0.0.15
- Fix: Gesamtes /config/data/ vor Neuinstallation bereinigen (nicht nur Admin-Ordner) — verhindert "Login already used" bei SQLite-DB-Resten

## 0.0.14
- Fix: Admin-Ordner in /config/data/ vor Neuinstallation bereinigen ("files already exist"-Fehler)

## 0.0.13
- Fix: occ-Pfad auf /app/www/src/occ korrigiert (linuxserver v33+: App im Image, nur config/apps/themes persistiert)

## 0.0.12
- Fix: occ per `find` suchen (maxdepth 3) statt hartem Pfad — fängt Strukturänderungen in linuxserver/nextcloud v33 ab
- Fix: Erweiterte Diagnostik im Warte-Loop (Inhalt /config/www/nextcloud/, find-Ergebnis)

## 0.0.11
- Fix: Nur /config/www/nextcloud/occ verwenden (persistente Instanz)
- Fix: exec tail -f /dev/null am Ende verhindert s6-Neustart-Loop
- Fix: Kein falscher occ-Aufruf auf /app/www/src/ mehr

## 0.0.10
- Fix: `--allow-root` → `ALLOW_ROOT=1` Umgebungsvariable (neues NC-Format)

## 0.0.9
- Fix: NC_CONFIG relativ zu OCC_BIN (neuer linuxserver Pfad /app/www/src/)
- Fix: Installations-Erkennung via `occ status` statt config.php-Check

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
