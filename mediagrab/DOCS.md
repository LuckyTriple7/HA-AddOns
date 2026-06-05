# MediaGrab — Dokumentation

## Konfiguration

| Option | Typ | Standard | Beschreibung |
|---|---|---|---|
| `username` | String | `admin` | Login-Benutzername |
| `password` | String | `secret` | Login-Passwort |
| `session_hours` | Integer | `24` | Session-Gültigkeitsdauer in Stunden |
| `max_concurrent` | Integer | `3` | Maximale parallele Downloads |
| `auto_clear_hours` | Integer | `0` | Fertige Jobs nach X Stunden löschen (0 = deaktiviert) |
| `speed_limit` | String | `""` | Downloadgeschwindigkeit begrenzen (z.B. `5M`, `500K`) |
| `api_key` | String | `""` | API-Key für REST-Sensoren (leer = deaktiviert) |
| `verbose_log` | Boolean | `false` | yt-dlp Ausgabe vollständig loggen |

## Verwendung

1. Add-on starten
2. Web-UI öffnen (Port 17791)
3. Mit Benutzername und Passwort anmelden
4. URL einfügen, Format wählen, auf **Herunterladen** klicken
5. Fortschritt in der Download-Queue beobachten
6. Fertige Dateien im Datei-Browser abspielen, herunterladen oder löschen

## Batch-Download

Mehrere URLs gleichzeitig — eine pro Zeile im URL-Feld:

```
https://www.youtube.com/watch?v=AAA
https://www.tiktok.com/@user/video/BBB
https://www.instagram.com/reel/CCC
```

## Unterstützte Formate

| Format | Beschreibung |
|---|---|
| Bestes Video (MP4) | Höchste verfügbare Qualität als MP4 |
| 1080p / 720p / 480p / 360p | Video mit maximaler Höhe |
| Audio (MP3) | Nur Audio, als MP3 (beste Qualität) |
| Audio (M4A) | Nur Audio, als M4A/AAC |

## Cookies (für private / altersgeschützte Videos)

1. Browser-Extension **"Get cookies.txt LOCALLY"** installieren (Chrome/Firefox)
2. Auf der jeweiligen Seite eingeloggt sein
3. Cookies exportieren (`.txt`-Datei)
4. In MediaGrab unter **Einstellungen → Cookies → Hinzufügen** hochladen
5. Mehrere Dateien (z.B. Instagram + TikTok) können nacheinander hinzugefügt werden

Cookies werden in `/data/cookies.txt` zusammengeführt und beim Download per "Cookies verwenden"-Checkbox aktiviert.

## Speicherort

Alle Dateien werden in `/media/mediagrab` gespeichert und sind über den HA Media-Browser zugänglich.

## Brute-Force-Schutz

Nach 5 fehlgeschlagenen Login-Versuchen wird die IP-Adresse für 15 Minuten gesperrt.

---

## REST API für Home Assistant Sensoren

### Einrichtung

1. Einen sicheren API-Key in den Add-on-Optionen setzen (z.B. `mein-geheimer-key-abc123`)
2. Add-on neu starten
3. Sensoren in `configuration.yaml` eintragen (siehe unten)

### API-Endpunkt

```
GET http://<HA-IP>:17791/api/status?api_key=DEIN_KEY
```

**Antwort-Beispiel:**
```json
{
  "active_downloads": 2,
  "done_downloads": 5,
  "error_downloads": 0,
  "files_count": 42,
  "folder_size_mb": 1842.3,
  "disk_free_gb": 18.5,
  "disk_used_pct": 63.4,
  "last_file": "Video Title.mp4",
  "ytdlp_version": "2026.03.17"
}
```

Der API-Key kann als URL-Parameter (`?api_key=...`) oder als Header (`X-API-Key: ...`) übergeben werden.

### HA configuration.yaml — alle Sensoren

```yaml
sensor:
  - platform: rest
    name: "MediaGrab Aktive Downloads"
    unique_id: mediagrab_active_downloads
    resource: "http://localhost:17791/api/status?api_key=DEIN_KEY"
    method: GET
    scan_interval: 30
    value_template: "{{ value_json.active_downloads }}"
    icon: mdi:download
    unit_of_measurement: ""

  - platform: rest
    name: "MediaGrab Fertige Downloads"
    unique_id: mediagrab_done_downloads
    resource: "http://localhost:17791/api/status?api_key=DEIN_KEY"
    method: GET
    scan_interval: 30
    value_template: "{{ value_json.done_downloads }}"
    icon: mdi:download-circle

  - platform: rest
    name: "MediaGrab Fehlerhafte Downloads"
    unique_id: mediagrab_error_downloads
    resource: "http://localhost:17791/api/status?api_key=DEIN_KEY"
    method: GET
    scan_interval: 30
    value_template: "{{ value_json.error_downloads }}"
    icon: mdi:download-off

  - platform: rest
    name: "MediaGrab Anzahl Dateien"
    unique_id: mediagrab_files_count
    resource: "http://localhost:17791/api/status?api_key=DEIN_KEY"
    method: GET
    scan_interval: 60
    value_template: "{{ value_json.files_count }}"
    icon: mdi:folder-play

  - platform: rest
    name: "MediaGrab Ordnergröße"
    unique_id: mediagrab_folder_size
    resource: "http://localhost:17791/api/status?api_key=DEIN_KEY"
    method: GET
    scan_interval: 60
    value_template: "{{ value_json.folder_size_mb }}"
    unit_of_measurement: "MB"
    icon: mdi:database

  - platform: rest
    name: "MediaGrab Freier Speicher"
    unique_id: mediagrab_disk_free
    resource: "http://localhost:17791/api/status?api_key=DEIN_KEY"
    method: GET
    scan_interval: 300
    value_template: "{{ value_json.disk_free_gb }}"
    unit_of_measurement: "GB"
    icon: mdi:harddisk

  - platform: rest
    name: "MediaGrab Speicher belegt"
    unique_id: mediagrab_disk_used_pct
    resource: "http://localhost:17791/api/status?api_key=DEIN_KEY"
    method: GET
    scan_interval: 300
    value_template: "{{ value_json.disk_used_pct }}"
    unit_of_measurement: "%"
    icon: mdi:harddisk

  - platform: rest
    name: "MediaGrab Letzte Datei"
    unique_id: mediagrab_last_file
    resource: "http://localhost:17791/api/status?api_key=DEIN_KEY"
    method: GET
    scan_interval: 30
    value_template: "{{ value_json.last_file }}"
    icon: mdi:file-video

  - platform: rest
    name: "MediaGrab yt-dlp Version"
    unique_id: mediagrab_ytdlp_version
    resource: "http://localhost:17791/api/status?api_key=DEIN_KEY"
    method: GET
    scan_interval: 3600
    value_template: "{{ value_json.ytdlp_version }}"
    icon: mdi:package-variant
```

> **Hinweis:** `localhost` ersetzen wenn HA und MediaGrab auf unterschiedlichen Hosts laufen. Bei Verwendung über Cloudflare Tunnel die externe URL einsetzen.

### Automation-Beispiel: Benachrichtigung bei fertigem Download

```yaml
automation:
  - alias: "MediaGrab Download fertig"
    trigger:
      - platform: state
        entity_id: sensor.mediagrab_letzte_datei
    condition:
      - condition: template
        value_template: "{{ trigger.to_state.state != trigger.from_state.state }}"
    action:
      - service: notify.mobile_app
        data:
          title: "MediaGrab ✅"
          message: "{{ trigger.to_state.state }} wurde heruntergeladen"
```

## Unterstützte Seiten

Alle von [yt-dlp](https://github.com/yt-dlp/yt-dlp) unterstützten Seiten — YouTube, Vimeo, TikTok, Instagram, SoundCloud, Twitch, Twitter/X, Reddit, Dailymotion und viele mehr.

Vollständige Liste: https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md
