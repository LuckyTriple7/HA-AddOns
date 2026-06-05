# Changelog — MediaGrab

## [0.2.3] — 2026-06-05
### Added
- Plattform-Filter in der Dateiliste: Filter-Buttons (YouTube, TikTok, Instagram, X, …) erscheinen automatisch wenn Dateien aus verschiedenen Quellen vorhanden sind
- Kleines Plattform-Badge je Datei (z.B. "YouTube") in der Datei-Metazeile
- Plattform wird beim Download in `.mediagrab_meta.json` gespeichert und beim Löschen bereinigt

## [0.2.2] — 2026-06-05
### Fixed
- API-Logging: log.debug() funktionierte nicht (Logger läuft auf INFO) — jetzt verbose_log-Prüfung wie beim yt-dlp-Logging

## [0.2.1] — 2026-06-05
### Fixed
- API `/api/status`: yt-dlp-Version wird 1h gecacht (kein subprocess bei jedem Sensor-Poll mehr)
- API `/api/status`: try-except schützt vor "unavailable" im HA-Sensor bei unerwarteten Fehlern
- API Logging: ungültige Key-Versuche immer als WARNING; erfolgreiche Zugriffe als INFO wenn verbose_log aktiv

## [0.2.0] — 2026-06-05
### Fixed
- Polling-Interval: _pollInterval war im falschen Scope — jetzt global, 500ms greift korrekt bei aktiven Downloads

## [0.1.9] — 2026-06-05
### Improved
- Polling-Interval dynamisch: 500ms bei aktiven Downloads, 2s im Leerlauf

## [0.1.8] — 2026-06-05
### Fixed
- Fortschrittsbalken: --progress-template statt Regex-Parsing — yt-dlp schreibt jetzt ein eigenes sauberes Format (MGPROG|28.3%|2.50MiB/s|00:52) das zuverlässig geparst wird

## [0.1.7] — 2026-06-05
### Fixed
- Temp-Dateien (.part, .ytdl) werden nach Abbruch, Fehler und Add-on-Neustart automatisch gelöscht
- Dateien aktiver Downloads bleiben unangetastet

## [0.1.6] — 2026-06-05
### Fixed
- Fortschrittsbalken Live-Update: for-Iterator durch readline()-Schleife ersetzt (kein interner Read-Ahead-Buffer mehr)
- Progress-Regex robuster: matched jetzt auch "Unknown" Speed/ETA am Download-Anfang

## [0.1.5] — 2026-06-05
### Added
- REST API `/api/status` für HA-Sensoren (gesichert per API-Key)
- 9 Sensor-Werte: aktive/fertige/fehlerhafte Downloads, Dateianzahl, Ordnergröße, freier Speicher, Speicherauslastung, letzte Datei, yt-dlp Version
- API-Key als URL-Parameter oder X-API-Key Header
- DOCS.md: vollständiges YAML-Beispiel für alle Sensoren + Automation-Beispiel

## [0.1.4] — 2026-06-05
### Fixed
- Fortschrittsbalken zeigte nur 0% → 100% (kein Live-Update)
- Ursache: yt-dlp pufferte Ausgabe in Pipe — behoben via PYTHONUNBUFFERED=1

## [0.1.3] — 2026-06-05
### Improved
- Dateiliste: zweizeiliges Layout — Dateiname oben (volle Breite), Größe/Datum/Buttons unten
- Bessere Lesbarkeit auf Mobile und Desktop

## [0.1.2] — 2026-06-05
### Added
- Play-Button (▶) in der Dateiliste für Video- und Audio-Dateien
- Video/Audio-Player öffnet sich als Modal direkt im Browser
- Schließen per ×-Button, Klick auf Hintergrund oder Escape-Taste
- Neuer /stream/-Endpunkt für Inline-Wiedergabe (ohne erzwungenen Download)

## [0.1.1] — 2026-06-05
### Fixed
- URL-Textarea: Resize-Griff rechts unten entfernt

## [0.1.0] — 2026-06-05
### Improved
- Cookies-Anzeige zeigt jetzt die enthaltenen Domains (z.B. "instagram.com, tiktok.com") statt nur die Dateigröße
- Tooltip zeigt Dateigröße und Anzahl Domains beim Hover

## [0.0.9] — 2026-06-05
### Fixed
- Cookies-Upload überschrieb bisherige Cookies — jetzt werden sie zusammengeführt (Instagram + TikTok gleichzeitig möglich)
- Upload-Button heißt nun "Hinzufügen" statt "Hochladen"

## [0.0.8] — 2026-06-05
### Added
- Translations (DE/EN) für alle Optionen in der HA-Konfigurationsoberfläche

## [0.0.7] — 2026-06-05
### Added
- "Cookies verwenden"-Checkbox im Download-Formular (erscheint nur wenn Cookies geladen sind)
- Cookies können pro Download ein- oder ausgeschaltet werden

### Fixed
- Downloads schlugen fehl wenn mehrere/ungültige Cookies hochgeladen wurden

## [0.0.6] — 2026-06-05
### Removed
- PWA-Installationsbanner entfernt (Browser-Favicon ausreichend)

## [0.0.5] — 2026-06-05
### Fixed
- Favicon in Browser-Tab fehlte (link rel="icon" ergänzt)

## [0.0.4] — 2026-06-05
### Added
- Batch-Download: mehrere URLs gleichzeitig (eine pro Zeile)
- Video-Info-Vorschau: Titel, Kanal, Dauer, Thumbnail vor dem Download
- Speicherplatz-Anzeige mit farbiger Fortschrittsleiste
- Datei-Suche und Sortierung (Datum / Name / Größe)
- Cookies-Support für private und altersgeschützte Videos
- yt-dlp manuell updaten per Button
- Queue überlebt Add-on Neustart (Persistenz via /data/jobs.json)
- Auto-Clear Queue konfigurierbar (auto_clear_hours)
- Geschwindigkeitsbegrenzung konfigurierbar (speed_limit)
- Verständliche Fehlermeldungen (Altersschutz, privat, nicht verfügbar, ...)

## [0.0.3] — 2026-06-05
### Added
- "Queue leeren"-Button: entfernt alle fertigen/fehlerhaften/abgebrochenen Jobs auf einmal (laufende Downloads bleiben)

## [0.0.2] — 2026-06-05
### Added
- Web Share Target: URL direkt vom Handy-Teilen-Menü an MediaGrab senden
- PWA-Installation erforderlich; Download startet nach dem Teilen automatisch

## [0.0.1] — 2026-06-05
### Added
- Erstveröffentlichung
- Web-GUI für yt-dlp (YouTube, Vimeo, SoundCloud, TikTok u.v.m.)
- Format-Auswahl: Bestes Video (MP4), 1080p/720p/480p/360p, Audio (MP3/M4A)
- Optionen: Untertitel, Ganze Playlist
- Live Download-Queue mit Fortschrittsbalken, Geschwindigkeit und ETA
- Datei-Browser für /media/mediagrab mit Download & Löschen
- Passwortschutz mit Brute-Force-Schutz (5 Versuche, 15 min Sperre)
- Mehrsprachig: Deutsch & Englisch
- Dark Mode / Light Mode mit System-Persistenz
- PWA-fähig (installierbar als App)
- Speicherort: /media/mediagrab
