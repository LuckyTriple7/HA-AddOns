# Webtop XFCE – Home Assistant Add-on

![GitHub Stars](https://img.shields.io/github/stars/LuckyTriple7/HA-AddOns?style=flat-square)
![Commits](https://img.shields.io/github/commit-activity/t/LuckyTriple7/HA-AddOns?style=flat-square&label=commits)
![Last Commit](https://img.shields.io/github/last-commit/LuckyTriple7/HA-AddOns?path=ubuntu-webtop&style=flat-square)

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

Debian Bookworm wird bis ca. 2028 mit Sicherheits-Updates versorgt. Firefox und Thunderbird werden direkt aus Mozillas offiziellem Debian-Repository installiert und sind daher immer aktuell (Stand: letzter Rebuild).

## Features

- **XFCE Desktop** im Browser – kein VNC-Client oder RDP nötig
- **KasmVNC-Streaming** – CPU-effizient durch delta-basiertes Bildschirm-Streaming
- **Systemsprache Deutsch** – Locale, Datum, Firefox-UI und Thunderbird auf Deutsch eingestellt
- **Firefox** (aktuell, aus Mozillas offiziellem Repository)
- **Thunderbird** E-Mail-Client (deutsch)
- **Thunar** Dateimanager mit SMB/CIFS-Netzwerkzugriff (`smb://server/share`)
- **Firefox** (aktuell, aus Mozillas offiziellem Repository)
- **Thunderbird** E-Mail-Client (deutsch)
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
| `PASSWORD` | leer | Passwortschutz für den Web-Zugang (Benutzername: `abc`) |
| `KEYBOARD` | leer | Tastaturlayout (z. B. `de-de-qwertz`) |
| `DRINODE` | leer | GPU-Gerät für Hardwarebeschleunigung (z. B. `/dev/dri/renderD128`) |

### Empfehlung für Intel-CPUs mit integrierter Grafik

Für Intel NUC, Intel Core i3/i5/i7/i9 mit Intel Integrated Graphics empfiehlt sich:

```
DRINODE: /dev/dri/renderD128
```

KasmVNC nutzt dann **Intel Quick Sync** für hardware-beschleunigtes Video-Encoding, was die CPU-Last beim Streaming spürbar reduziert.

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

## App-Updates und Sicherheits-Patches

Der laufende Container bekommt **keine automatischen Updates** — Pakete sind zum Zeitpunkt des Builds eingefroren. Sicherheits-Patches kommen erst beim nächsten Rebuild:

> **Empfehlung:** Einmal im Monat **„Neu aufbauen"** klicken. Dabei werden alle Debian-Sicherheits-Patches der letzten Wochen sowie das aktuelle LinuxServer.io-Base-Image gezogen.

Ein Klick auf **„Neu aufbauen"** baut das Docker-Image neu und zieht dabei aktualisierte Versionen — je nach App:

| App | Rebuild reicht? |
|---|---|
| Firefox, Thunderbird | ✓ Ja — aus Mozillas Repo, immer aktuell |
| VS Code | ✓ Ja — aus Microsofts Repo, immer aktuell |
| Bitwarden | ✓ Ja — neueste Version via GitHub API automatisch ermittelt |
| Geany, gedit, gThumb, VLC, LibreOffice, Ristretto, Remmina, Baobab, Seahorse u.a. | Nur Sicherheits-Updates — Debian Stable liefert keine neuen Major-Versionen |
| Angry IP Scanner | ✗ Nein — Version fest im Dockerfile hinterlegt, muss manuell angepasst werden |

## VS Code

VS Code ist aus Microsofts offiziellem apt-Repository installiert und immer aktuell nach einem Rebuild.

- **Extension Marketplace** funktioniert vollständig — Extensions können wie unter Windows über das Extensions-Panel installiert werden
- **Einstellungen und Extensions** werden in `/addon_configs/ubuntu_webtop/.config/Code/` gespeichert und bleiben über Rebuilds und Neustarts erhalten
- **Kein Auto-Update im Container**: VS Code's eingebauter Updater ist deaktiviert (`update.mode: none`) — Updates kommen automatisch mit dem nächsten **„Neu aufbauen"** des Add-ons
- **Terminal**: VS Code's integriertes Terminal funktioniert im Container

## Audio

Audio wird über den integrierten PulseAudio-Dienst des Base-Images bereitgestellt und direkt im Browser wiedergegeben — ohne externe Abhängigkeiten oder hassio_audio.

- **Browser-Audio**: YouTube, Mediaplayer und andere Web-Apps spielen Ton direkt im Browser-Tab ab
- **VLC**: Nutzt PulseAudio automatisch
- **Kein hassio_audio**: `audio: false` verhindert CPU-Spikes durch Audio-Retry-Schleifen (`audio: true` hat früher 50–60 % Host-CPU verursacht)

## Bekannte Einschränkungen

- **Kein automatischer CIFS-Kernel-Mount**: Der Linux-Kernel-CIFS-Mount (`mount -t cifs`) ist im HA-Container-Sicherheitsmodell nicht verfügbar. SMB-Zugriff funktioniert über Thunar (gvfs/userspace).
- **xfce4-session deaktiviert**: In HA-Containern fehlen systemd-Dienste (polkit, logind). XFCE-Komponenten werden direkt gestartet.
- **SESSION_MANAGER Warnungen** im Log sind harmlos und können ignoriert werden.

## Unterstützte Architekturen

- `amd64` (x86_64)
- `aarch64` (ARM64, z. B. Raspberry Pi 4/5)
