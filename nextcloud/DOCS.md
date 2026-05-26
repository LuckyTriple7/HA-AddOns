# Nextcloud

Nextcloud direkt in Home Assistant — private Cloud mit Web-UI und SMB-Netzwerkspeicher-Unterstützung.

## Zugriff

Nach dem Start erreichbar unter: **`https://<HA-IP>:7443`**

> Das Add-on läuft nicht als HA-Ingress-Panel — direkter Portzugriff ist erforderlich.

## Ersteinrichtung

1. Add-on starten
2. `https://<HA-IP>:7443` im Browser öffnen (Sicherheitswarnung für selbstsigniertes Zertifikat akzeptieren)
3. Web-Installer ausfüllen — Datenverzeichnis: `/config/data`
4. Add-on **neu starten** — alle Konfigurationen werden automatisch angewendet

## Konfiguration

| Option | Standard | Beschreibung |
|--------|----------|--------------|
| `PUID` | `1000` | User-ID für Dateiberechtigungen |
| `PGID` | `1000` | Group-ID für Dateiberechtigungen |
| `TZ` | `Europe/Berlin` | Zeitzone |
| `trusted_domains` | — | Zusätzliche Domains/IPs (kommagetrennt, z.B. `192.168.1.100,meinserver.de`) |
| `trusted_proxies` | `172.30.32.0/23` | IP/Subnetz des Reverse-Proxys (z.B. NGINX Proxy Manager) |
| `default_phone_region` | `DE` | Standard-Telefonregion (ISO 3166-1) |
| `enable_thumbnails` | `true` | Vorschaubilder für Fotos und Videos generieren |
| `memory_limit` | `512M` | PHP-Speicherlimit |
| `upload_max_filesize` | `512M` | Maximale Upload-Dateigröße |
| `post_max_size` | `512M` | Maximale POST-Größe (muss ≥ upload_max_filesize sein) |
| `disable_updates` | `false` | Nextcloud-Webupdate deaktivieren |
| `maintenance_window_start` | `1` | Startzeit Wartungsfenster in UTC (0–23) |
| `loglevel` | `3` | Log-Level: 0=Debug, 1=Info, 2=Warning, 3=Error, 4=Fatal |
| `mariadb_discovery` | `false` | HA MariaDB Add-on automatisch erkennen (aus = SQLite) |
| `smb_1_server` | — | IP/Hostname des SMB-Servers (Slot 1) |
| `smb_1_share` | — | Name des SMB-Shares (Slot 1) |
| `smb_1_user` | — | Benutzername (Slot 1) |
| `smb_1_password` | — | Passwort (Slot 1) |
| `smb_2_*` / `smb_3_*` | — | SMB-Slots 2 und 3 (analog zu Slot 1) |

## Web-Terminal (occ-Befehle)

Erreichbar über **„Nextcloud Terminal"** in der HA-Seitenleiste. Alle Befehle mit Präfix:

```sh
ALLOW_ROOT=1 php /app/www/public/occ <befehl>
```

| Befehl | Beschreibung |
|--------|-------------|
| `occ status` | Nextcloud-Status anzeigen |
| `occ files:scan --all` | Dateien neu einlesen |
| `occ db:add-missing-indices` | Fehlende DB-Indizes hinzufügen |
| `occ maintenance:repair` | Reparatur ausführen |
| `occ user:list` | Benutzer anzeigen |
| `occ user:resetpassword <user>` | Passwort zurücksetzen |
| `occ security:bruteforce:reset <IP>` | IP-Sperre aufheben |
| `occ log:tail` | Live-Log anzeigen |

## Datenspeicherort

```
/addon_configs/nextcloud/
├── data/          ← Benutzerdateien
├── www/nextcloud/ ← Nextcloud-Konfiguration (config.php)
└── php/           ← PHP-Konfiguration
```

---

# Nextcloud (English)

Nextcloud directly in Home Assistant — private cloud with web UI and SMB network storage support.

## Access

After startup, available at: **`https://<HA-IP>:7443`**

> The add-on does not run as an HA Ingress panel — direct port access is required.

## First Setup

1. Start the add-on
2. Open `https://<HA-IP>:7443` in your browser (accept the security warning for the self-signed certificate)
3. Complete the web installer — data directory: `/config/data`
4. **Restart** the add-on — all settings are applied automatically

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `PUID` | `1000` | User ID for file permissions |
| `PGID` | `1000` | Group ID for file permissions |
| `TZ` | `Europe/Berlin` | Timezone |
| `trusted_domains` | — | Additional domains/IPs (comma-separated, e.g. `192.168.1.100,myserver.de`) |
| `trusted_proxies` | `172.30.32.0/23` | IP/subnet of reverse proxy (e.g. NGINX Proxy Manager) |
| `default_phone_region` | `DE` | Default phone region (ISO 3166-1) |
| `enable_thumbnails` | `true` | Generate preview images for photos and videos |
| `memory_limit` | `512M` | PHP memory limit |
| `upload_max_filesize` | `512M` | Maximum upload file size |
| `post_max_size` | `512M` | Maximum POST size (must be ≥ upload_max_filesize) |
| `disable_updates` | `false` | Disable Nextcloud web update |
| `maintenance_window_start` | `1` | Maintenance window start in UTC (0–23) |
| `loglevel` | `3` | Log level: 0=Debug, 1=Info, 2=Warning, 3=Error, 4=Fatal |
| `mariadb_discovery` | `false` | Auto-detect HA MariaDB add-on (off = SQLite) |
| `smb_1_server` | — | IP/hostname of SMB server (slot 1) |
| `smb_1_share` | — | Share name (slot 1) |
| `smb_1_user` | — | Username (slot 1) |
| `smb_1_password` | — | Password (slot 1) |
| `smb_2_*` / `smb_3_*` | — | SMB slots 2 and 3 (same as slot 1) |

## Web Terminal (occ Commands)

Accessible via **"Nextcloud Terminal"** in the HA sidebar. All commands use the prefix:

```sh
ALLOW_ROOT=1 php /app/www/public/occ <command>
```

| Command | Description |
|---------|-------------|
| `occ status` | Show Nextcloud status |
| `occ files:scan --all` | Re-scan files |
| `occ db:add-missing-indices` | Add missing DB indices |
| `occ maintenance:repair` | Run repair |
| `occ user:list` | List users |
| `occ user:resetpassword <user>` | Reset password |
| `occ security:bruteforce:reset <IP>` | Remove brute-force block |
| `occ log:tail` | Show live log |

## Data Location

```
/addon_configs/nextcloud/
├── data/          ← User files
├── www/nextcloud/ ← Nextcloud configuration (config.php)
└── php/           ← PHP configuration
```
