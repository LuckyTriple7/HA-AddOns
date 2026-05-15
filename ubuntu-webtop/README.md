# Webtop XFCE – Home Assistant Add-on

Vollständiger XFCE-Desktop, zugänglich über jeden modernen Webbrowser – direkt in Home Assistant integriert. Basiert auf dem KasmVNC-Streaming-Stack von [LinuxServer.io](https://www.linuxserver.io).

## Features

- **XFCE Desktop** im Browser – kein VNC-Client oder RDP nötig
- **KasmVNC-Streaming** – CPU-effizient durch delta-basiertes Bildschirm-Streaming
- **Systemsprache Deutsch** – Locale, Datum, Firefox-UI und Thunderbird auf Deutsch eingestellt
- **Firefox** (aktuell, aus Mozillas offiziellem Repository)
- **Thunderbird** E-Mail-Client (deutsch)
- **Thunar** Dateimanager mit SMB/CIFS-Netzwerkzugriff (`smb://server/share`)
- **Geany** Code- und Texteditor
- **VLC** Mediaplayer
- **Ristretto** Bildbetrachter
- **Atril** PDF-Betrachter
- **Galculator** Taschenrechner
- **Xarchiver** Archiv-Manager (ZIP, TAR, ...)
- **nmap** Netzwerkscanner
- **GNOME Keyring** – Passwörter für Netzwerk-Shares werden dauerhaft gespeichert
- Persistente Konfiguration über Add-on-Updates hinweg (`/config`)
- Zugriff auf Home Assistant Shares (`/share`, `/media`, SSL-Zertifikate)

## Installation

1. Repository in Home Assistant hinzufügen:
   **Einstellungen → Add-ons → Add-on Store → ⋮ → Repositories**
   URL: `https://github.com/LuckyTriple7/HA-AddOns`

2. Add-on **Webtop XFCE** suchen und installieren

3. Konfiguration anpassen (optional, siehe unten)

4. Add-on starten

## Zugriff

| Protokoll | URL |
|-----------|-----|
| HTTP  | `http://<HA-IP>:7776` |
| HTTPS | `https://<HA-IP>:7777` |

Ist ein Passwort gesetzt, erscheint ein Login-Dialog:
- **Benutzername:** `abc`
- **Passwort:** das in der Konfiguration eingetragene Passwort

## Konfiguration

| Option | Standard | Beschreibung |
|--------|----------|--------------|
| `PUID` | `1000` | Benutzer-ID des Desktop-Users |
| `PGID` | `1000` | Gruppen-ID des Desktop-Users |
| `TZ` | `Europe/Berlin` | Zeitzone (z. B. `Europe/Vienna`) |
| `PASSWORD` | leer | Passwortschutz für den Web-Zugang (Benutzername: `abc`) |
| `KEYBOARD` | leer | Tastaturlayout (z. B. `de-de-qwertz`) |
| `DRINODE` | leer | GPU-Gerät für Hardwarebeschleunigung (z. B. `/dev/dri/renderD128`) |

## Netzwerk-Shares (SMB/CIFS)

SMB-Shares können direkt in Thunar geöffnet werden:

1. Thunar öffnen → Adressleiste mit **Strg+L** aktivieren
2. Adresse eingeben: `smb://192.168.178.x/sharename`
3. Benutzername und Passwort eingeben
4. **„Passwort merken"** auswählen → wird dauerhaft im GNOME Keyring gespeichert

## Persistente Daten

Alle Benutzereinstellungen (Desktop-Konfiguration, Lesezeichen, Passwörter) werden in `/addon_configs/ubuntu_webtop/` gespeichert und bleiben über Updates und Neustarts erhalten.

| Pfad im Container | Inhalt |
|-------------------|--------|
| `/config` | Persistente Add-on-Konfiguration |
| `/share` | HA Share-Verzeichnis |
| `/media` | HA Media-Verzeichnis |

## Bekannte Einschränkungen

- **Kein automatischer CIFS-Kernel-Mount**: Der Linux-Kernel-CIFS-Mount (`mount -t cifs`) ist im HA-Container-Sicherheitsmodell nicht verfügbar. SMB-Zugriff funktioniert über Thunar (gvfs/userspace).
- **xfce4-session deaktiviert**: In HA-Containern fehlen systemd-Dienste (polkit, logind). XFCE-Komponenten werden direkt gestartet.
- **SESSION_MANAGER Warnungen** im Log sind harmlos und können ignoriert werden.

## Unterstützte Architekturen

- `amd64` (x86_64)
- `aarch64` (ARM64, z. B. Raspberry Pi 4/5)
