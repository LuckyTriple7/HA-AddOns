# Nextcloud

![GitHub Stars](https://img.shields.io/github/stars/LuckyTriple7/HA-AddOns?style=flat-square)
![Commits](https://img.shields.io/github/commit-activity/t/LuckyTriple7/HA-AddOns?style=flat-square&label=commits)
![Last Commit](https://img.shields.io/github/last-commit/LuckyTriple7/HA-AddOns?path=nextcloud&style=flat-square)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/luckytriple7)

Nextcloud direkt in Home Assistant — private Cloud mit Web-UI, REST-API und SMB-Netzwerkspeicher-Unterstützung.

> **Beta:** Dieses Add-on befindet sich in der Entwicklung. Für den produktiven Einsatz empfiehlt sich eine vollständige Nextcloud-Installation auf einem dedizierten Server.

## Zugriff

Nach dem Start ist Nextcloud erreichbar unter:

- **HTTP:** `http://<HA-IP>:7780`
- **HTTPS:** `https://<HA-IP>:7443`

Das Add-on läuft **nicht** als HA-Ingress-Panel — der direkte Portzugriff ist erforderlich.

## Funktionen

- **Nextcloud**: Vollständige Nextcloud-Instanz auf Basis des linuxserver.io-Images
- **SQLite**: Datenbank für den Heimgebrauch (kein PostgreSQL/MySQL erforderlich)
- **addon_config-Speicher**: Alle Daten liegen unter `/addon_configs/nextcloud/` — überleben Add-on-Updates
- **SMB-Mounts**: Bis zu 3 Netzwerklaufwerke als externe Speicher einbinden
- **PHP-Limits**: Speicher, Upload- und POST-Größe frei konfigurierbar
- **Thumbnails**: Vorschaubilder aktivierbar
- **Updates**: Nextcloud-Webupdate deaktivierbar für mehr Kontrolle

## Konfiguration

| Option | Standard | Beschreibung |
|--------|----------|--------------|
| `PUID` | `1000` | User-ID für Dateiberechtigungen |
| `PGID` | `1000` | Group-ID für Dateiberechtigungen |
| `TZ` | `Europe/Berlin` | Zeitzone |
| `admin_user` | `admin` | Anzeigename des Admin-Nutzers |
| `admin_password` | — | Passwort für den Admin-Nutzer |
| `trusted_domains` | — | Kommagetrennte Liste zusätzlicher Domains/IPs (z.B. `192.168.1.100,meinserver.local`) |
| `default_phone_region` | `DE` | Standard-Telefonregion (ISO 3166-1 Alpha-2, z.B. `DE`, `AT`, `CH`) |
| `enable_thumbnails` | `true` | Vorschaubilder für Fotos und Videos generieren |
| `memory_limit` | `512M` | PHP-Speicherlimit |
| `upload_max_filesize` | `512M` | Maximale Upload-Dateigröße |
| `post_max_size` | `512M` | Maximale POST-Größe |
| `disable_updates` | `false` | Nextcloud-Webupdate deaktivieren |
| `smb_1_server` | — | IP/Hostname des SMB-Servers (Slot 1) |
| `smb_1_share` | — | Name des SMB-Shares (Slot 1) |
| `smb_1_user` | — | Benutzername für den SMB-Share (Slot 1) |
| `smb_1_password` | — | Passwort für den SMB-Share (Slot 1) |
| `smb_2_*` | — | SMB-Slot 2 (analog zu Slot 1) |
| `smb_3_*` | — | SMB-Slot 3 (analog zu Slot 1) |

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
├── data/          ← Benutzerdateien
├── www/nextcloud/ ← Nextcloud-Installation
├── php/           ← PHP-Konfiguration
└── log/           ← Logs
```

Die Daten bleiben bei Add-on-Updates, Neustarts und Neuinstallationen erhalten.

## Updates

Dieses Add-on nutzt das vorgefertigte Image von `ghcr.io/luckytriple7/nextcloud`. Ein GitHub Actions Workflow prüft regelmäßig auf neue Nextcloud-Versionen und baut bei Bedarf automatisch ein neues Image.

Zum Aktualisieren:
1. **Einstellungen → Add-ons → Nextcloud → Aktualisieren** (falls eine neue Version verfügbar ist)
2. Oder manuell: **Neu aufbauen** um das aktuelle Image zu laden

→ [Changelog](CHANGELOG.md)

---

# Nextcloud (English)

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/luckytriple7)

Nextcloud directly in Home Assistant — private cloud with web UI, REST API and SMB network storage support.

> **Beta:** This add-on is under development. For production use, a full Nextcloud installation on a dedicated server is recommended.

## Access

After startup, Nextcloud is available at:

- **HTTP:** `http://<HA-IP>:7780`
- **HTTPS:** `https://<HA-IP>:7443`

The add-on does **not** run as an HA Ingress panel — direct port access is required.

## Features

- **Nextcloud**: Full Nextcloud instance based on the linuxserver.io image
- **SQLite**: Database for home use (no PostgreSQL/MySQL required)
- **addon_config storage**: All data stored under `/addon_configs/nextcloud/` — survives add-on updates
- **SMB mounts**: Mount up to 3 network drives as external storage
- **PHP limits**: Memory, upload and POST size freely configurable
- **Thumbnails**: Preview image generation configurable
- **Updates**: Nextcloud web update can be disabled for more control

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `PUID` | `1000` | User ID for file permissions |
| `PGID` | `1000` | Group ID for file permissions |
| `TZ` | `Europe/Berlin` | Timezone |
| `admin_user` | `admin` | Display name of admin user |
| `admin_password` | — | Password for the admin user |
| `trusted_domains` | — | Comma-separated list of additional domains/IPs (e.g. `192.168.1.100,myserver.local`) |
| `default_phone_region` | `DE` | Default phone region (ISO 3166-1 Alpha-2, e.g. `DE`, `AT`, `CH`) |
| `enable_thumbnails` | `true` | Generate preview images for photos and videos |
| `memory_limit` | `512M` | PHP memory limit |
| `upload_max_filesize` | `512M` | Maximum upload file size |
| `post_max_size` | `512M` | Maximum POST size |
| `disable_updates` | `false` | Disable Nextcloud web update |
| `smb_1_server` | — | IP/hostname of SMB server (slot 1) |
| `smb_1_share` | — | Name of SMB share (slot 1) |
| `smb_1_user` | — | Username for SMB share (slot 1) |
| `smb_1_password` | — | Password for SMB share (slot 1) |
| `smb_2_*` | — | SMB slot 2 (same as slot 1) |
| `smb_3_*` | — | SMB slot 3 (same as slot 1) |

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
├── data/          ← User files
├── www/nextcloud/ ← Nextcloud installation
├── php/           ← PHP configuration
└── log/           ← Logs
```

Data is preserved across add-on updates, restarts, and reinstallations.

## Updates

This add-on uses the pre-built image from `ghcr.io/luckytriple7/nextcloud`. A GitHub Actions workflow regularly checks for new Nextcloud versions and automatically builds a new image when needed.

To update:
1. **Settings → Add-ons → Nextcloud → Update** (if a new version is available)
2. Or manually: **Rebuild** to pull the current image
