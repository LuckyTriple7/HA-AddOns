# FileBox

![GitHub Stars](https://img.shields.io/github/stars/LuckyTriple7/HA-AddOns?style=flat-square)
![Commits](https://img.shields.io/github/commit-activity/t/LuckyTriple7/HA-AddOns?style=flat-square&label=commits)
![Last Commit](https://img.shields.io/github/last-commit/LuckyTriple7/HA-AddOns?path=filebox&style=flat-square)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/luckytriple7)
![Docker](https://img.shields.io/badge/docker-ghcr.io-blue?style=flat-square&logo=docker)

Web-Oberfläche zum Hoch- und Herunterladen von Dateien direkt in Home Assistant — basierend auf [FileBrowser](https://filebrowser.xyz).

## Funktionen

- Dateien hochladen, herunterladen und verwalten
- Standardmäßig Zugriff auf `/share/filebox`
- Optionaler Zugriff auf weitere HA-Shares (`/media`, `/config`, `/backup`)
- **SMB-Netzlaufwerke** — bis zu 5 Netzwerk-Shares (NAS, Windows, Samba) direkt einbinden
- Konfigurierbarer Benutzername und Passwort
- Deutsche Benutzeroberfläche
- Weitere Benutzer können direkt in der Oberfläche angelegt werden

## Konfiguration

| Option | Typ | Standard | Beschreibung |
|---|---|---|---|
| `port` | int | `17771` | Port der Web-Oberfläche |
| `username` | str | `admin` | Benutzername des Admin-Kontos |
| `password` | str | `admin1234567` | Passwort des Admin-Kontos |
| `show_media` | bool | `false` | `/media` als Ordner einblenden |
| `show_config` | bool | `false` | `/config` als Ordner einblenden |
| `show_backup` | bool | `false` | `/backup` als Ordner einblenden |
| `smb_1_server` | str | — | IP oder Hostname des SMB-Servers (z. B. `192.168.178.10`) |
| `smb_1_share` | str | — | Share-Name (optional — leer lässt alle Shares automatisch erkennen) |
| `smb_1_user` | str | — | Benutzername (leer = Gastzugang) |
| `smb_1_password` | str | — | Passwort |

Die Felder `smb_2_*` bis `smb_5_*` funktionieren identisch für weitere Server.

## SMB-Netzlaufwerke

SMB-Shares (NAS, Windows-Freigaben, Samba) werden beim Start automatisch gemountet und in FileBrowser als Ordner angezeigt.

**Share-Name leer lassen** → alle verfügbaren Disk-Shares des Servers werden automatisch erkannt und einzeln eingebunden (`SMB-1 Cloud`, `SMB-1 Backup` usw.).

**Share-Name angeben** → nur dieser eine Share wird gemountet.

> **Hinweis:** Das Add-on benötigt `SYS_ADMIN`-Rechte für Kernel-CIFS-Mounts. Diese werden automatisch gesetzt.

## Passwort-Verwaltung

**Wichtig:** Benutzername und Passwort des ersten Admin-Kontos werden bei **jedem Start** aus der Add-on-Konfiguration übernommen. Änderungen direkt in der FileBrowser-Oberfläche werden beim nächsten Neustart überschrieben.

→ Passwort immer in den **Add-on-Optionen** (HA-Einstellungen) ändern, nicht in FileBrowser selbst.

Weitere Benutzer, die du in der Oberfläche anlegst, sind davon **nicht betroffen** — sie bleiben dauerhaft erhalten.

## Dateiablage

Dateien landen standardmäßig unter `/share/filebox` — im selben Bereich, in dem auch andere Add-ons (z. B. Firefox DE) ihre Downloads ablegen.

## Automatische Updates

Ein GitHub-Actions-Workflow prüft täglich, ob eine neue FileBrowser-Version verfügbar ist. Bei einem Update wird automatisch ein Pull Request mit neuem Image und aktualisiertem Changelog erstellt.

## Changelog

Siehe [CHANGELOG.md](CHANGELOG.md).
