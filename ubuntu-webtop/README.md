# Webtop XFCE – Home Assistant Add-on

![GitHub Stars](https://img.shields.io/github/stars/LuckyTriple7/HA-AddOns?style=flat-square)
![Commits](https://img.shields.io/github/commit-activity/t/LuckyTriple7/HA-AddOns?style=flat-square&label=commits)
![Last Commit](https://img.shields.io/github/last-commit/LuckyTriple7/HA-AddOns?path=ubuntu-webtop&style=flat-square)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/luckytriple7)

Vollständiger XFCE-Desktop, zugänglich über jeden modernen Webbrowser – direkt in Home Assistant integriert. Basiert auf dem KasmVNC-Streaming-Stack von [LinuxServer.io](https://www.linuxserver.io).

## Basis-Image

Dieses Add-on basiert auf:

**`ghcr.io/linuxserver/baseimage-kasmvnc:debianbookworm`**

| | |
|---|---|
| **Anbieter** | [LinuxServer.io](https://www.linuxserver.io) |
| **Betriebssystem** | Debian 12 (Bookworm) |
| **Streaming** | KasmVNC 1.3.x – delta-basiert, CPU-effizient |
| **Init-System** | s6-overlay v3 |
| **Desktop-User** | `abc` (UID 1000) |

Debian Bookworm wird bis ca. 2028 mit Sicherheits-Updates versorgt. Firefox, Thunderbird, VS Code und GitHub CLI werden aus den offiziellen Repositories der jeweiligen Hersteller installiert. Bitwarden und Angry IP Scanner werden als gepinnte Versionen via GitHub Releases bezogen — ein GitHub Actions Workflow prüft täglich auf neue Versionen.

## Features

- **XFCE Desktop** im Browser – kein VNC-Client oder RDP nötig
- **KasmVNC-Streaming** – CPU-effizient durch delta-basiertes Bildschirm-Streaming
- **Systemsprache Deutsch** – Locale, Datum, Firefox-UI und Thunderbird auf Deutsch eingestellt
- **Firefox** (aktuell, aus Mozillas offiziellem Repository)
- **Thunderbird** E-Mail-Client (deutsch)
- **Thunar** Dateimanager mit SMB/CIFS-Netzwerkzugriff (`smb://server/share`)
- **LibreOffice** Writer, Calc, Impress (deutsch)
- **Geany** Code- und Texteditor mit Syntax-Highlighting
- **gedit** Texteditor — öffnet SMB-Dateien aus Thunar direkt ohne Wrapper
- **gThumb** Bildeditor — Bilder verkleinern, zuschneiden, aus SMB-Shares direkt öffnen
- **Ristretto** Bildbetrachter
- **Flameshot** Screenshot-Tool mit Annotations
- **Atril** PDF-Betrachter
- **VS Code** Code-Editor mit Extension Marketplace (aktuell, aus Microsofts offiziellem Repository)
- **VLC** Mediaplayer
- **Remmina** RDP/VNC/SSH Remote-Desktop-Client (inkl. RDP- und VNC-Plugin)
- **Bitwarden** Passwort-Manager (Desktop-App)
- **Angry IP Scanner** Netzwerk-Scanner (GUI)
- **PuTTY** SSH-Client
- **Galculator** Taschenrechner
- **Xarchiver** Archiv-Manager (ZIP, TAR, ...)
- **nmap** Netzwerkscanner (CLI)
- **Baobab** Speicherplatz-Analyse (grafisch)
- **Seahorse** GNOME Keyring GUI — gespeicherte Passwörter verwalten (Menü: *Zubehör → Passwörter und Schlüssel*)
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
| `PASSWORD` | leer | Passwortschutz für den Web-Zugang — Benutzername ist immer `abc` |
| `KEYBOARD` | leer | Tastaturlayout (z. B. `de-de-qwertz`) |
| `DRINODE` | leer | GPU-Gerät für Hardwarebeschleunigung (z. B. `/dev/dri/renderD128`) |
| `show_media` | `false` | HA-Media-Share (`/media`) als Thunar-Lesezeichen einblenden |
| `show_backup` | `false` | HA-Backup-Share (`/backup`) als Thunar-Lesezeichen einblenden |
| `smb_1_server` … `smb_5_server` | leer | IP oder Hostname des SMB-Servers (Slot 1–5) |
| `smb_1_share` … `smb_5_share` | leer | Name des SMB-Shares (z. B. `backup`) |
| `smb_1_user` … `smb_5_user` | leer | Benutzername für den SMB-Zugang (leer = Gastzugang) |
| `smb_1_password` … `smb_5_password` | leer | Passwort für den SMB-Zugang |

### Empfehlung für Intel-CPUs mit integrierter Grafik

Für Intel NUC, Intel Core i3/i5/i7/i9 mit Intel Integrated Graphics empfiehlt sich:

```
DRINODE: /dev/dri/renderD128
```

KasmVNC nutzt dann **Intel Quick Sync** für hardware-beschleunigtes Video-Encoding, was die CPU-Last beim Streaming spürbar reduziert.

## Netzwerk-Shares (SMB/CIFS)

### Automatisches Mounten beim Start (empfohlen)

Bis zu 5 SMB-Shares können in der Add-on-Konfiguration eingetragen werden und werden beim Start automatisch als CIFS-Kernel-Mount eingehängt. Die Shares erscheinen anschließend als Thunar-Lesezeichen.

**Beispiel für Slot 1:**
```
smb_1_server: 192.168.178.100
smb_1_share:  backup
smb_1_user:   homeassistant
smb_1_password: meinPasswort
```

Die Shares sind nach dem Start unter `/mnt/smb1` bis `/mnt/smb5` erreichbar — auch für Apps die kein GVFS unterstützen (z. B. VLC, Terminal).

Für Gastzugang einfach `smb_x_user` und `smb_x_password` leer lassen.

### Manuell via Thunar (ohne Neustart)

SMB-Shares können auch ohne Konfiguration direkt in Thunar geöffnet werden:

1. Thunar öffnen → Adressleiste mit **Strg+L** aktivieren
2. Adresse eingeben: `smb://192.168.178.x/sharename`
3. Benutzername und Passwort eingeben
4. **„Passwort merken"** auswählen → wird dauerhaft im GNOME Keyring gespeichert

> **Hinweis:** Der manuelle Thunar-Zugriff läuft über GVFS (Userspace). Nur GIO-fähige Apps (Thunar, gedit, Totem) können diese Verbindung nutzen. Für VLC und andere Apps empfiehlt sich das automatische Mounten via Konfiguration.

## Persistente Daten

Alle Benutzereinstellungen (Desktop-Konfiguration, Lesezeichen, Passwörter) werden in `/addon_configs/ubuntu_webtop/` gespeichert und bleiben über Updates und Neustarts erhalten.

| Pfad im Container | Inhalt |
|-------------------|--------|
| `/config` | Persistente Add-on-Konfiguration |
| `/share` | HA Share-Verzeichnis |
| `/media` | HA Media-Verzeichnis |

## App-Updates und Sicherheits-Patches

Der laufende Container bekommt **keine automatischen Updates** — Pakete sind zum Zeitpunkt des Builds eingefroren.

### Wie Updates funktionieren

Ein **GitHub Actions Workflow** prüft täglich um 3:00 Uhr UTC auf neue Versionen der folgenden Pakete:

| Paket | Quelle |
|-------|--------|
| Bitwarden | GitHub Releases |
| VS Code | Microsoft apt-Repository |
| GitHub CLI | GitHub Releases |
| Firefox | Mozilla apt-Repository |
| Thunderbird | Mozilla apt-Repository |
| Angry IP Scanner | GitHub Releases |

Sobald eine neue Version erkannt wird, erstellt der Workflow automatisch einen **Pull Request** in diesem Repository.

**Update-Ablauf:**
1. PR im GitHub-Repository mergen
2. In Home Assistant erscheint automatisch die neue Add-on-Version — **„Aktualisieren"** klicken

„Aktualisieren" zieht die neue Version und baut das Image dabei neu.

Beim Rebuild werden nicht nur die oben gelisteten Pakete aktualisiert — auch **LibreOffice, VLC, Remmina, Geany** und alle anderen Debian-Pakete erhalten beim Rebuild die aktuellen Sicherheits-Updates aus dem Debian-Repository.

> **Hinweis:** Ein **„Neu aufbauen"** ohne vorherigen Update-Schritt (ohne gemergten PR) bringt keine neuen Paketversionen, da Docker den Build-Cache verwendet.

## VS Code

VS Code ist aus Microsofts offiziellem apt-Repository installiert. Der Workflow prüft täglich auf neue Versionen und erstellt bei Bedarf automatisch einen PR — nach Merge und Rebuild ist VS Code aktuell.

- **Extension Marketplace** funktioniert vollständig — Extensions können wie unter Windows über das Extensions-Panel installiert werden
- **Einstellungen und Extensions** werden in `/addon_configs/ubuntu_webtop/.config/Code/` gespeichert und bleiben über Rebuilds und Neustarts erhalten
- **Kein Auto-Update im Container**: VS Code's eingebauter Updater ist deaktiviert (`update.mode: none`) — Updates kommen automatisch mit dem nächsten **„Neu aufbauen"** des Add-ons
- **Terminal**: VS Code's integriertes Terminal funktioniert im Container

## Cloud-Speicher (OneDrive, Google Drive, …)

rclone ist vorinstalliert und ermöglicht den Zugriff auf OneDrive, Google Drive, Dropbox und weitere Cloud-Anbieter als lokales Laufwerk — ähnlich wie Files-On-Demand unter Windows. Dateien werden erst beim Öffnen heruntergeladen.

### Einrichtung (einmalig im Terminal)

1. **Terminal öffnen** (im Webtop-Desktop) und rclone konfigurieren:
   ```
   rclone config
   ```
   → Remote-Typ wählen (z. B. `onedrive`), Anleitung im Browser folgen.
   Die Konfiguration wird dauerhaft in `/config/.config/rclone/rclone.conf` gespeichert.

2. **Add-on neu starten** — rclone mountet beim nächsten Start alle konfigurierten Remotes automatisch.

### Wie es funktioniert

- Beim Start liest das Skript alle Remotes aus `rclone.conf` und startet für jeden einen lokalen WebDAV-Server (`rclone serve webdav`, Port 8800, 8801, …).
- Jeder Remote erscheint als Thunar-Lesezeichen (`dav://localhost:8800/` usw.) in der Seitenleiste.
- Dateien werden erst beim Öffnen heruntergeladen — kein vollständiger Sync (echtes Files-on-Demand).
- Schreibzugriff ist möglich; Änderungen werden sofort hochgeladen.
- Kein FUSE, keine Kernel-Module nötig — funktioniert in HA-Containern ohne Sonder-Privileges.

### Hinweis

Die Ersteinrichtung (`rclone config`) erfordert kurz einen Browser für die OAuth-Anmeldung — dieser ist im Webtop bereits vorhanden.

## Audio

Audio wird über den integrierten PulseAudio-Dienst des Base-Images bereitgestellt und direkt im Browser wiedergegeben — ohne externe Abhängigkeiten oder hassio_audio.

- **Browser-Audio**: YouTube, Mediaplayer und andere Web-Apps spielen Ton direkt im Browser-Tab ab
- **VLC**: Nutzt PulseAudio automatisch
- **Kein hassio_audio**: `audio: false` verhindert CPU-Spikes durch Audio-Retry-Schleifen (`audio: true` hat früher 50–60 % Host-CPU verursacht)

## Bekannte Einschränkungen

- **xfce4-session deaktiviert**: In HA-Containern fehlen systemd-Dienste (polkit, logind). XFCE-Komponenten werden direkt gestartet.
- **SESSION_MANAGER Warnungen** im Log sind harmlos und können ignoriert werden.

## Unterstützte Architekturen

- `amd64` (x86_64)
- `aarch64` (ARM64, z. B. Raspberry Pi 4/5)
