# Nextcloud

![GitHub Stars](https://img.shields.io/github/stars/LuckyTriple7/HA-AddOns?style=flat-square)
![Commits](https://img.shields.io/github/commit-activity/t/LuckyTriple7/HA-AddOns?style=flat-square&label=commits)
![Last Commit](https://img.shields.io/github/last-commit/LuckyTriple7/HA-AddOns?path=nextcloud&style=flat-square)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/luckytriple7)

Nextcloud direkt in Home Assistant — private Cloud mit Web-UI und SMB-Netzwerkspeicher-Unterstützung.

## Zugriff

Nach dem Start ist Nextcloud erreichbar unter:

- **HTTPS:** `https://<HA-IP>:7443`

Das Add-on läuft **nicht** als HA-Ingress-Panel — der direkte Portzugriff ist erforderlich.

## Ersteinrichtung

1. Add-on starten
2. Browser öffnen: `https://<HA-IP>:7443` (Browser-Sicherheitswarnung beim selbstsignierten Zertifikat akzeptieren)
3. Web-Installer ausfüllen — Datenverzeichnis: `/config/data`
4. Add-on **neu starten** — alle Konfigurationen (trusted_domains etc.) werden automatisch angewendet

## Funktionen

- **Nextcloud**: Vollständige Nextcloud-Instanz auf Basis des linuxserver.io-Images
- **SQLite**: Datenbank für den Heimgebrauch (kein PostgreSQL/MySQL erforderlich)
- **addon_config-Speicher**: Alle Daten liegen unter `/addon_configs/nextcloud/` — überleben Add-on-Updates
- **SMB-Mounts**: Bis zu 3 Netzwerklaufwerke als externe Speicher einbinden
- **PHP-Limits**: Speicher, Upload- und POST-Größe frei konfigurierbar
- **Thumbnails**: Vorschaubilder aktivierbar
- **Web-Terminal**: occ-Befehle direkt im Browser ausführbar (HA Ingress)
- **Automatische Updates**: GitHub Actions prüft täglich auf neue Nextcloud-Versionen

## Konfiguration

| Option | Standard | Beschreibung |
|--------|----------|--------------|
| `PUID` | `1000` | User-ID für Dateiberechtigungen |
| `PGID` | `1000` | Group-ID für Dateiberechtigungen |
| `TZ` | `Europe/Berlin` | Zeitzone |
| `trusted_domains` | — | Kommagetrennte Liste zusätzlicher Domains/IPs (z.B. `192.168.1.100,meinserver.de`) |
| `trusted_proxies` | `172.30.32.0/23` | IP/Subnetz des Reverse-Proxys (z.B. NGINX Proxy Manager) — verhindert Brute-Force-Drosselung |
| `default_phone_region` | `DE` | Standard-Telefonregion (ISO 3166-1, z.B. `DE`, `AT`, `CH`) |
| `enable_thumbnails` | `true` | Vorschaubilder für Fotos und Videos generieren |
| `memory_limit` | `512M` | PHP-Speicherlimit |
| `upload_max_filesize` | `512M` | Maximale Upload-Dateigröße |
| `post_max_size` | `512M` | Maximale POST-Größe (muss ≥ upload_max_filesize sein) |
| `disable_updates` | `false` | Nextcloud-Webupdate deaktivieren |
| `run_db_indices` | `false` | Fehlende DB-Indizes beim Start hinzufügen (`occ db:add-missing-indices`) — danach wieder deaktivieren |
| `maintenance_window_start` | `1` | Startzeit Wartungsfenster in UTC (0–23, z.B. 1 = 2–3 Uhr DE) |
| `loglevel` | `3` | Log-Level: 0=Debug, 1=Info, 2=Warning, 3=Error, 4=Fatal |
| `skeletondirectory` | — | Vorlageordner für neue Benutzer (leer = keine Demo-Dateien) |
| `trashbin_retention_obligation` | `auto, 30` | Aufbewahrung gelöschter Dateien (z.B. `auto, 30` = max. 30 Tage) |
| `versions_retention_obligation` | `auto, 30` | Aufbewahrung von Datei-Versionen (z.B. `auto, 30` = max. 30 Tage) |
| `mariadb_discovery` | `false` | HA MariaDB Add-on automatisch erkennen und nutzen (aus = SQLite) |
| `smb_1_server` | — | IP/Hostname des SMB-Servers (Slot 1) |
| `smb_1_share` | — | Name des SMB-Shares (Slot 1) |
| `smb_1_user` | — | Benutzername für den SMB-Share (Slot 1) |
| `smb_1_password` | — | Passwort für den SMB-Share (Slot 1) |
| `smb_2_*` | — | SMB-Slot 2 (analog zu Slot 1) |
| `smb_3_*` | — | SMB-Slot 3 (analog zu Slot 1) |

## Web-Terminal (occ-Befehle)

Das Add-on enthält ein Web-Terminal, erreichbar über den **„Nextcloud Terminal"-Eintrag in der HA-Seitenleiste**. Dort können `occ`-Befehle direkt ausgeführt werden.

Alle Befehle mit folgendem Präfix:
```sh
ALLOW_ROOT=1 php /app/www/public/occ <befehl>
```

**Nützliche Befehle:**

| Befehl | Beschreibung |
|--------|-------------|
| `occ status` | Nextcloud-Status anzeigen |
| `occ app:list` | Installierte Apps anzeigen |
| `occ app:enable <app>` | App aktivieren |
| `occ app:disable <app>` | App deaktivieren |
| `occ files:scan --all` | Dateien neu einlesen (nach manuellem Upload) |
| `occ files:cleanup` | Verwaiste Dateieinträge bereinigen |
| `occ db:add-missing-indices` | Fehlende DB-Indizes hinzufügen |
| `occ maintenance:repair` | Nextcloud-Reparatur ausführen |
| `occ security:bruteforce:reset <IP>` | IP-Sperre der Brute-Force-Erkennung aufheben |
| `occ user:list` | Benutzer anzeigen |
| `occ user:resetpassword <user>` | Passwort zurücksetzen |
| `occ log:tail` | Live-Log anzeigen |
| `occ list` | Alle verfügbaren Befehle anzeigen |

## SMB-Netzwerkspeicher

Konfigurierte SMB-Shares werden beim Start automatisch gemountet und in Nextcloud als **externe Speicher** eingebunden (App „External storage support" wird automatisch aktiviert).

**Beispiel:**
```
smb_1_server: 192.168.1.10
smb_1_share: Fotos
smb_1_user: peter
smb_1_password: geheim
```

Der Share erscheint dann in Nextcloud als „SMB-1 Fotos".

## Speicherort der Daten

Alle Nextcloud-Daten (Dateien, Datenbank, Konfiguration) liegen im HA-Konfigurationsordner:

```
/addon_configs/nextcloud/
├── data/          ← Benutzerdateien + nextcloud.log
├── www/nextcloud/ ← Nextcloud-Konfiguration (config.php)
├── php/           ← PHP-Konfiguration
└── keys/          ← SSL-Zertifikate
```

Die Daten bleiben bei Add-on-Updates, Neustarts und Neuinstallationen erhalten.

## Updates

Ein GitHub Actions Workflow prüft täglich auf neue Nextcloud-Versionen (linuxserver.io-Image) und baut bei Bedarf automatisch ein neues Image. Zum Aktualisieren in HA: **Einstellungen → Add-ons → Nextcloud → Aktualisieren**.

→ [Changelog](CHANGELOG.md)

---

# Nextcloud (English)

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/luckytriple7)

Nextcloud directly in Home Assistant — private cloud with web UI and SMB network storage support.

## Access

After startup, Nextcloud is available at:

- **HTTPS:** `https://<HA-IP>:7443`

The add-on does **not** run as an HA Ingress panel — direct port access is required.

## First Setup

1. Start the add-on
2. Open browser: `https://<HA-IP>:7443` (accept the browser security warning for the self-signed certificate)
3. Complete web installer — data directory: `/config/data`
4. **Restart** the add-on — all settings (trusted_domains etc.) are applied automatically

## Features

- **Nextcloud**: Full Nextcloud instance based on the linuxserver.io image
- **SQLite**: Database for home use (no PostgreSQL/MySQL required)
- **addon_config storage**: All data stored under `/addon_configs/nextcloud/` — survives add-on updates
- **SMB mounts**: Mount up to 3 network drives as external storage
- **PHP limits**: Memory, upload and POST size freely configurable
- **Thumbnails**: Preview image generation configurable
- **Web terminal**: Run occ commands directly in the browser (HA Ingress)
- **Automatic updates**: GitHub Actions checks daily for new Nextcloud versions

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `PUID` | `1000` | User ID for file permissions |
| `PGID` | `1000` | Group ID for file permissions |
| `TZ` | `Europe/Berlin` | Timezone |
| `trusted_domains` | — | Comma-separated list of additional domains/IPs (e.g. `192.168.1.100,myserver.de`) |
| `trusted_proxies` | `172.30.32.0/23` | IP/subnet of reverse proxy (e.g. NGINX Proxy Manager) — prevents brute-force throttling |
| `default_phone_region` | `DE` | Default phone region (ISO 3166-1, e.g. `DE`, `AT`, `CH`) |
| `enable_thumbnails` | `true` | Generate preview images for photos and videos |
| `memory_limit` | `512M` | PHP memory limit |
| `upload_max_filesize` | `512M` | Maximum upload file size |
| `post_max_size` | `512M` | Maximum POST size (must be ≥ upload_max_filesize) |
| `disable_updates` | `false` | Disable Nextcloud web update |
| `run_db_indices` | `false` | Add missing DB indices on startup (`occ db:add-missing-indices`) — disable again afterwards |
| `maintenance_window_start` | `1` | Maintenance window start in UTC (0–23, e.g. 1 = 2–3 AM DE) |
| `loglevel` | `3` | Log level: 0=Debug, 1=Info, 2=Warning, 3=Error, 4=Fatal |
| `skeletondirectory` | — | Template folder for new users (empty = no demo files) |
| `trashbin_retention_obligation` | `auto, 30` | Deleted files retention (e.g. `auto, 30` = max. 30 days) |
| `versions_retention_obligation` | `auto, 30` | File version retention (e.g. `auto, 30` = max. 30 days) |
| `mariadb_discovery` | `false` | Auto-detect and use HA MariaDB add-on (off = SQLite) |
| `smb_1_server` | — | IP/hostname of SMB server (slot 1) |
| `smb_1_share` | — | Name of SMB share (slot 1) |
| `smb_1_user` | — | Username for SMB share (slot 1) |
| `smb_1_password` | — | Password for SMB share (slot 1) |
| `smb_2_*` | — | SMB slot 2 (same as slot 1) |
| `smb_3_*` | — | SMB slot 3 (same as slot 1) |

## Web Terminal (occ Commands)

The add-on includes a web terminal, accessible via the **"Nextcloud Terminal" entry in the HA sidebar**. From there, `occ` commands can be executed directly.

All commands use the following prefix:
```sh
ALLOW_ROOT=1 php /app/www/public/occ <command>
```

**Useful commands:**

| Command | Description |
|---------|-------------|
| `occ status` | Show Nextcloud status |
| `occ app:list` | List installed apps |
| `occ app:enable <app>` | Enable an app |
| `occ app:disable <app>` | Disable an app |
| `occ files:scan --all` | Re-scan files (after manual upload) |
| `occ files:cleanup` | Clean up orphaned file entries |
| `occ db:add-missing-indices` | Add missing database indices |
| `occ maintenance:repair` | Run Nextcloud repair |
| `occ security:bruteforce:reset <IP>` | Remove brute-force block for an IP |
| `occ user:list` | List users |
| `occ user:resetpassword <user>` | Reset user password |
| `occ log:tail` | Show live log |
| `occ list` | Show all available commands |

## SMB Network Storage

Configured SMB shares are automatically mounted at startup and registered in Nextcloud as **external storage** (the "External storage support" app is enabled automatically).

**Example:**
```
smb_1_server: 192.168.1.10
smb_1_share: Photos
smb_1_user: peter
smb_1_password: secret
```

The share will appear in Nextcloud as "SMB-1 Photos".

## Data Location

All Nextcloud data (files, database, configuration) is stored in the HA config folder:

```
/addon_configs/nextcloud/
├── data/          ← User files + nextcloud.log
├── www/nextcloud/ ← Nextcloud configuration (config.php)
├── php/           ← PHP configuration
└── keys/          ← SSL certificates
```

Data is preserved across add-on updates, restarts, and reinstallations.

## Updates

A GitHub Actions workflow checks daily for new Nextcloud versions (linuxserver.io image) and automatically builds a new image when needed. To update in HA: **Settings → Add-ons → Nextcloud → Update**.

→ [Changelog](CHANGELOG.md)
