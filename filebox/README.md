# FileBox

Web-Oberfläche zum Hoch- und Herunterladen von Dateien direkt in Home Assistant — basierend auf [FileBrowser](https://filebrowser.xyz).

## Funktionen

- Dateien hochladen, herunterladen und verwalten
- Standardmäßig Zugriff auf `/share/filebox`
- Optionaler Zugriff auf weitere HA-Shares (`/media`, `/config`, `/backup`)
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
