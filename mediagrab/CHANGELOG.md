# Changelog — MediaGrab

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
