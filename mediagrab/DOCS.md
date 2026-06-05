# MediaGrab — Dokumentation

## Konfiguration

| Option | Typ | Standard | Beschreibung |
|---|---|---|---|
| `username` | String | `admin` | Login-Benutzername |
| `password` | String | `secret` | Login-Passwort |
| `session_hours` | Integer | `24` | Session-Gültigkeitsdauer in Stunden |
| `max_concurrent` | Integer | `3` | Maximale parallele Downloads |
| `verbose_log` | Boolean | `false` | yt-dlp-Ausgabe im Log anzeigen |

## Verwendung

1. Add-on starten
2. Web-UI öffnen (Port 17791)
3. Mit Benutzername und Passwort anmelden
4. URL einfügen, Format wählen, auf **Herunterladen** klicken
5. Fortschritt in der Download-Queue beobachten
6. Fertige Dateien im Datei-Browser herunterladen oder löschen

## Speicherort

Alle Dateien werden in `/media/mediagrab` gespeichert.
Dieser Ordner ist auch über den HA Media-Browser zugänglich.

## Unterstützte Formate

- **Bestes Video (MP4)** — höchste verfügbare Qualität als MP4
- **1080p / 720p / 480p / 360p** — Video mit maximaler Höhe
- **Audio (MP3)** — nur Audio, als MP3 (beste Qualität)
- **Audio (M4A)** — nur Audio, als M4A/AAC

## Optionen beim Download

- **Untertitel** — lädt verfügbare Untertitel (DE + EN) als .vtt-Dateien mit
- **Ganze Playlist** — lädt die gesamte Playlist herunter (standard: nur einzelnes Video)

## Brute-Force-Schutz

Nach 5 fehlgeschlagenen Login-Versuchen wird die IP-Adresse für 15 Minuten gesperrt.

## Unterstützte Seiten

Alle von yt-dlp unterstützten Seiten, u.a.:
YouTube, Vimeo, SoundCloud, TikTok, Twitch, Twitter/X, Reddit, Dailymotion und viele mehr.

Vollständige Liste: https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md
