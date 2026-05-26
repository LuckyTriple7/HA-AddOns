# Webtop XFCE

Vollständiger XFCE-Desktop im Browser, direkt in Home Assistant integriert.

## Zugriff

| Protokoll | URL |
|-----------|-----|
| HTTP | `http://<HA-IP>:7776` |
| HTTPS | `https://<HA-IP>:7777` |

Bei gesetztem Passwort: Benutzername `abc`, Passwort wie in der Konfiguration.

## Konfiguration

| Option | Standard | Beschreibung |
|--------|----------|--------------|
| `PUID` | `1000` | Benutzer-ID des Desktop-Users |
| `PGID` | `1000` | Gruppen-ID des Desktop-Users |
| `TZ` | `Europe/Berlin` | Zeitzone (z.B. `Europe/Vienna`) |
| `PASSWORD` | — | Passwortschutz für den Web-Zugang (Benutzername: `abc`) |
| `KEYBOARD` | — | Tastaturlayout (z.B. `de-de-qwertz`) |
| `DRINODE` | — | GPU-Gerät für Hardwarebeschleunigung (z.B. `/dev/dri/renderD128`) |
| `show_media` | `false` | HA-Media-Share als Thunar-Lesezeichen |
| `show_backup` | `false` | HA-Backup-Share als Thunar-Lesezeichen |
| `smb_1_server` | — | IP oder Hostname des SMB-Servers (Slot 1–5) |
| `smb_1_share` | — | Name des SMB-Shares |
| `smb_1_user` | — | Benutzername (leer = Gastzugang) |
| `smb_1_password` | — | Passwort |

> Für Intel NUC / Intel CPUs mit integrierter Grafik: `DRINODE: /dev/dri/renderD128` setzt Hardware-Encoding ein und reduziert die CPU-Last beim Streaming deutlich.

## Vorinstallierte Programme

- **Firefox** — aktuell, aus Mozillas offiziellem Repository
- **Thunderbird** — E-Mail-Client (deutsch)
- **LibreOffice** — Writer, Calc, Impress (deutsch)
- **VS Code** — Code-Editor mit Extension Marketplace
- **Bitwarden** — Passwort-Manager
- **Thunar** — Dateimanager mit SMB-Netzwerkzugriff
- **VLC** — Mediaplayer
- **Remmina** — RDP/VNC Remote-Desktop-Client
- **Angry IP Scanner** — Netzwerk-Scanner
- **Flameshot** — Screenshot-Tool
- **Geany / gedit** — Text- und Code-Editoren
- **gThumb** — Bildeditor
- **PuTTY** — SSH-Client
- **Claude Desktop** — KI-Assistent (Desktop-App)
- **rclone** — Cloud-Speicher (OneDrive, Google Drive, …)

## SMB-Netzlaufwerke

Bis zu 5 SMB-Shares in der Konfiguration eintragen — sie werden beim Start automatisch gemountet und als Thunar-Lesezeichen eingeblendet.

Manuell ohne Neustart via Thunar: Adressleiste mit `Strg+L` → `smb://192.168.178.x/sharename` eingeben.

## Cloud-Speicher (OneDrive, Google Drive, …)

rclone ist vorinstalliert. Einmalige Einrichtung im Terminal:

```bash
rclone config
```

Nach dem Neustart des Add-ons werden alle konfigurierten Remotes automatisch als Thunar-Lesezeichen gemountet (WebDAV, kein FUSE nötig).

**LibreOffice** kann Cloud-Dateien direkt über **Datei → Fernzugriff → WebDAV** öffnen (`http://localhost:8800/`).

## Persistente Daten

Alle Desktop-Einstellungen, Lesezeichen und Passwörter werden in `/addon_configs/ubuntu_webtop/` gespeichert und bleiben über Updates und Neustarts erhalten.

## Updates

Ein GitHub Actions Workflow prüft täglich auf neue Versionen von Firefox, Thunderbird, VS Code, Bitwarden, GitHub CLI, Angry IP Scanner und Claude Desktop. Bei einem Update wird automatisch ein PR erstellt — nach dem Merge erscheint die neue Version in HA.

---

# Webtop XFCE (English)

Full XFCE desktop in the browser, directly integrated into Home Assistant.

## Access

| Protocol | URL |
|----------|-----|
| HTTP | `http://<HA-IP>:7776` |
| HTTPS | `https://<HA-IP>:7777` |

If a password is set: username `abc`, password as configured.

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `PUID` | `1000` | User ID of the desktop user |
| `PGID` | `1000` | Group ID of the desktop user |
| `TZ` | `Europe/Berlin` | Timezone (e.g. `Europe/Vienna`) |
| `PASSWORD` | — | Password protection for web access (username: `abc`) |
| `KEYBOARD` | — | Keyboard layout (e.g. `de-de-qwertz`) |
| `DRINODE` | — | GPU device for hardware acceleration (e.g. `/dev/dri/renderD128`) |
| `show_media` | `false` | HA media share as Thunar bookmark |
| `show_backup` | `false` | HA backup share as Thunar bookmark |
| `smb_1_server` | — | IP or hostname of the SMB server (slots 1–5) |
| `smb_1_share` | — | Share name |
| `smb_1_user` | — | Username (empty = guest access) |
| `smb_1_password` | — | Password |

> For Intel NUC / Intel CPUs with integrated graphics: `DRINODE: /dev/dri/renderD128` enables hardware encoding and significantly reduces CPU load during streaming.

## Pre-installed Applications

- **Firefox** — up-to-date, from Mozilla's official repository
- **Thunderbird** — email client (German)
- **LibreOffice** — Writer, Calc, Impress (German)
- **VS Code** — code editor with Extension Marketplace
- **Bitwarden** — password manager
- **Thunar** — file manager with SMB network access
- **VLC** — media player
- **Remmina** — RDP/VNC remote desktop client
- **Angry IP Scanner** — network scanner
- **Flameshot** — screenshot tool
- **Geany / gedit** — text and code editors
- **gThumb** — image editor
- **PuTTY** — SSH client
- **Claude Desktop** — AI assistant (desktop app)
- **rclone** — cloud storage (OneDrive, Google Drive, …)

## SMB Network Drives

Enter up to 5 SMB shares in the configuration — they are automatically mounted on startup and shown as Thunar bookmarks.

Manually without restart via Thunar: activate address bar with `Ctrl+L` → enter `smb://192.168.178.x/sharename`.

## Cloud Storage (OneDrive, Google Drive, …)

rclone is pre-installed. One-time setup in the terminal:

```bash
rclone config
```

After restarting the add-on, all configured remotes are automatically mounted as Thunar bookmarks (WebDAV, no FUSE required).

**LibreOffice** can open cloud files directly via **File → Remote Files → WebDAV** (`http://localhost:8800/`).

## Persistent Data

All desktop settings, bookmarks and passwords are stored in `/addon_configs/ubuntu_webtop/` and persist across updates and restarts.

## Updates

A GitHub Actions workflow checks daily for new versions of Firefox, Thunderbird, VS Code, Bitwarden, GitHub CLI, Angry IP Scanner and Claude Desktop. When an update is found, a PR is created automatically — after merging, the new version appears in HA.
