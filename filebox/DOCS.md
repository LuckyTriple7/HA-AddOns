# FileBox

Web-Oberfläche zum Hoch- und Herunterladen von Dateien direkt in Home Assistant — basierend auf [FileBrowser](https://filebrowser.xyz).

## Einrichtung

1. Add-on starten
2. In der HA-Sidebar auf **FileBox** klicken
3. Mit dem konfigurierten Benutzernamen und Passwort anmelden

## Konfiguration

| Option | Standard | Beschreibung |
|--------|----------|--------------|
| `port` | `17771` | Port der Web-Oberfläche |
| `username` | `admin` | Benutzername des Admin-Kontos |
| `password` | `admin1234567` | Passwort des Admin-Kontos |
| `show_media` | `false` | `/media` als Ordner einblenden |
| `show_config` | `false` | `/config` als Ordner einblenden |
| `show_backup` | `false` | `/backup` als Ordner einblenden |
| `smb_1_server` | — | IP oder Hostname des SMB-Servers (z.B. `192.168.1.10`) |
| `smb_1_share` | — | Share-Name (leer = alle Shares automatisch erkennen) |
| `smb_1_user` | — | Benutzername (leer = Gastzugang) |
| `smb_1_password` | — | Passwort |

Die Felder `smb_2_*` bis `smb_5_*` funktionieren identisch für weitere Server.

## SMB-Netzlaufwerke

SMB-Shares (NAS, Windows-Freigaben, Samba) werden beim Start automatisch gemountet und als Ordner in FileBrowser angezeigt.

- **Share-Name leer lassen** → alle verfügbaren Disk-Shares des Servers werden automatisch erkannt
- **Share-Name angeben** → nur dieser eine Share wird gemountet

## Passwort-Verwaltung

Benutzername und Passwort werden bei **jedem Start** aus der Add-on-Konfiguration übernommen. Änderungen direkt in der FileBrowser-Oberfläche werden beim nächsten Neustart überschrieben.

→ Passwort immer in den **Add-on-Optionen** ändern, nicht in FileBrowser selbst.

Weitere Benutzer, die in der Oberfläche angelegt werden, bleiben dauerhaft erhalten.

## Dateiablage

Dateien landen standardmäßig unter `/share/filebox`.

---

# FileBox (English)

Web UI for uploading and downloading files directly in Home Assistant — based on [FileBrowser](https://filebrowser.xyz).

## Setup

1. Start the add-on
2. Click **FileBox** in the HA sidebar
3. Log in with the configured username and password

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `port` | `17771` | Port of the web UI |
| `username` | `admin` | Admin account username |
| `password` | `admin1234567` | Admin account password |
| `show_media` | `false` | Show `/media` as a folder |
| `show_config` | `false` | Show `/config` as a folder |
| `show_backup` | `false` | Show `/backup` as a folder |
| `smb_1_server` | — | IP or hostname of the SMB server (e.g. `192.168.1.10`) |
| `smb_1_share` | — | Share name (empty = auto-detect all shares) |
| `smb_1_user` | — | Username (empty = guest access) |
| `smb_1_password` | — | Password |

Fields `smb_2_*` through `smb_5_*` work identically for additional servers.

## SMB Network Drives

SMB shares (NAS, Windows shares, Samba) are automatically mounted on startup and appear as folders in FileBrowser.

- **Leave share name empty** → all available disk shares on the server are detected automatically
- **Enter share name** → only that specific share is mounted

## Password Management

Username and password are applied from the add-on configuration on **every startup**. Changes made directly in the FileBrowser UI will be overwritten on the next restart.

→ Always change the password in the **add-on options**, not in FileBrowser itself.

Additional users created in the UI are not affected — they persist permanently.

## File Storage

Files are stored by default under `/share/filebox`.
