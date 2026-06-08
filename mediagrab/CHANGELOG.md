# Changelog — MediaGrab

## [1.0.26.1] - 2026-06-08

Bump python from 3.11-alpine to 3.14-alpine


## [1.0.25] — 2026-06-08

### Security
- Open Redirect: `_safe_next()` gibt jetzt via `urlunsplit` zurück (Taint-Kette unterbrochen, CodeQL MEDIUM #36)
- Open Redirect: Neues `_allowed_next()` mit Allowlist `{'/'}` für Login-`next`-Parameter (CodeQL MEDIUM #37)
- Login-Route nutzt jetzt `_allowed_next` statt `_safe_next` (beide POST- und GET-Pfade)

## [1.0.24] — 2026-06-08

### Security
- Open Redirect: `_safe_next()` robuster — `isinstance`-Check, `strip()`, `//`-Präfix-Schutz, `urlsplit` statt `urlparse` (CodeQL MEDIUM #36, #37, #131)
- Open Redirect: `set_lang()` Referrer via `urlsplit`/`urlunsplit` auf Pfad/Query/Fragment reduziert vor Übergabe an `_safe_next()` (CodeQL MEDIUM #37)

## [1.0.23] — 2026-06-08

### Security
- Open Redirect: `_safe_next()` via `urlparse` verstärkt — Schema/Netloc-Prüfung statt reinem `/`-Check (CodeQL MEDIUM #36, #37, #131)

## [1.0.22] — 2026-06-08

### Security
- Cookie Injection: `cookie_lang` aus Literal statt URL-Parameter in `set_lang()` — Taint-Kette unterbrochen (CodeQL MEDIUM #50)

## [1.0.21] — 2026-06-08

### Security
- Command Injection: `cmd.append(url)` → `cmd += ['--', url]` in `_build_cmd`
- Information Exposure: `str(e)` in api_info, api_ytdlp_version, api_ytdlp_update durch `'internal error'` + `log.exception()` ersetzt (durch v1.0.2-Revert wieder reingerutscht)

## [1.0.20] — 2026-06-08

### Security
- Uncontrolled command line: URL-Kanonisierung via `urlsplit` vor yt-dlp — blockiert Credentials, Fragments und Control-Chars; übergibt nur `canonical_url` (CodeQL #757)

## [1.0.19] — 2026-06-08

### Security
- Uncontrolled command line: `cmd.append(url)` → `cmd += ['--', url]` in `api_info` — `--` trennt Flags von URL-Argument (CodeQL CRITICAL #756)

## [1.0.18] — 2026-06-08

### Changed
- `_safe_media_path()`: `secure_filename()`-Check entfernt (bricht Unicode-Dateinamen) — Path-basierte Checks bleiben erhalten

## [1.0.17] — 2026-06-08

### Security
- Path Injection: `_safe_media_path()` nutzt jetzt `werkzeug.secure_filename()` als primäre Sanitierung + Path-Checks als Backstop (CodeQL #51–#59)
- Route-Converter `<path:filename>` → `<filename>` für delete/platform/tag — verhindert `/` im URL-Parameter
- `is_file()`-Check vor `unlink()` — verhindert versehentliches Löschen von Verzeichnissen

## [1.0.16] — 2026-06-08

### Security
- SSRF: `_is_safe_external_media_url()` blockiert private/loopback/reserved IPs und localhost vor yt-dlp-Aufruf (`import ipaddress`)
- Path Injection: `_safe_media_path()` prüft absolute Pfade, Trennzeichen und `..` VOR `resolve()` — alle 9 Route-Handler nutzen jetzt diese Funktion (CodeQL HIGH #51–#59)

## [1.0.15] — 2026-06-08

### Security
- Incomplete URL substring sanitization: `_detect_platform()` nutzt jetzt `urlparse().hostname` + `_is_host()`-Helper statt `in url.lower()` — verhindert Bypass durch URLs wie `evil.com/youtube.com` (CodeQL #81)

## [1.0.14] — 2026-06-08

### Security
- Command Injection: URL-Validierung (`urlparse` scheme+netloc) in `api_info` und `api_download` vor yt-dlp-Aufruf (CodeQL HIGH #703)

## [1.0.13] — 2026-06-08

### Security
- Flask 3.0.3 → 3.1.3

### Changed
- Revert auf stabilen Stand v1.0.2 (Security-Fixes v1.0.3–v1.0.12 haben Streams gebrochen)

## [1.0.2] — 2026-06-07
### Added
- Disconnect-Erkennung: `visibilitychange` (Tab/Laptop-Aufklappen), `online`/`offline`-Events, `navigator.onLine`-Check beim Start
- Offline-Banner: abdunkelndes Overlay mit animiertem 📡, lokalisierten Texten (DE/EN) und „Neu laden"-Button

## [1.0.1] — 2026-06-07
### Improved
- **Multi-Tag-Filter**: Plattform- und Custom-Tags in der Dateiliste lassen sich jetzt mehrfach gleichzeitig auswählen (Klick toggelt, mehrere aktiv möglich)

## [1.0.0] — 2026-06-06
### First Stable Release
- **Platform-Tags**: automatische Erkennung (YouTube, TikTok, Instagram, X, Vimeo, SoundCloud, Twitch, Reddit, Dailymotion) + manuell zuweisbar per Klick; eigene Plattformnamen per Freitexteingabe möglich; Plattform-Filter in der Dateiliste
- **Custom-Tags**: freier Texttag pro Datei (gelb); Schnellauswahl aus vorhandenen Tags; unabhängig vom Plattform-Tag
- **Dateikonflikt-Handling**: neue Datei bekommt Zeitstempel-Suffix (`Video_20260606_123456.mp4`), bestehende Datei bleibt unverändert (Tags/Metadaten erhalten)
- **yt-dlp Update-Button**: prüft PyPI auf neue Version vor dem Update; zeigt „Bereits aktuell" wenn keine neuere Version vorhanden
- **PWA Share Format-Picker**: beim Teilen via PWA erscheint Bottom-Sheet mit 7 Format-Buttons statt sofortigem Download
- **In-App Console**: Doppelklick auf „MediaGrab" öffnet draggbares Floating-Window mit yt-dlp-Logs
- Sonderzeichen (Apostrophe etc.) in Dateinamen brechen keine onclick-Handler mehr (escJs-Fix)

## [0.4.1] — 2026-06-06
### Fixed
- Plattform-Picker: Backend lehnte eigene Plattformnamen mit "invalid_platform" ab — Validierung gegen feste Liste entfernt

## [0.4.0] — 2026-06-06
### Added
- Plattform-Picker: Texteingabe für eigene Plattformnamen unterhalb der vordefinierten Buttons — analog zum Custom-Tag-Popup; vorhandener Custom-Wert wird beim Öffnen vorausgefüllt

## [0.3.9] — 2026-06-06
### Added
- PWA Share: Format-Picker Modal erscheint beim Teilen eines Links — 7 Buttons (Bestes Video, 1080p–360p, MP3, M4A); kein automatischer Download mehr direkt nach dem Teilen

## [0.3.8] — 2026-06-06
### Changed
- DE: Download-Button heißt jetzt "Download" statt "Herunterladen"

## [0.3.7] — 2026-06-06
### Fixed
- Apostroph/Sonderzeichen in Dateinamen (z.B. "What's up.mp4") brachen alle onclick-Handler (Play, Delete, Tags) lautlos — escJs() Funktion ergänzt die ' und \ für JS-String-Kontext escaped

## [0.3.6] — 2026-06-06
- Fix: Nur INFO-Logs in Console — Root-StreamHandler auf INFO gesetzt, Root-Logger auf DEBUG; _buf_h (DEBUG) sieht alle Level, HA-Log bleibt bei INFO+. yt-dlp Zeilen immer als DEBUG in Buffer (unabhängig von verbose_log)

## [0.3.5] — 2026-06-06
- Neu: In-App Console (Doppelklick auf "MediaGrab") — draggbares Floating-Window; Python _BufferHandler erfasst alle Log-Aufrufe inkl. yt-dlp Output-Zeilen; GET /api/logs?since=; localStorage-Persistenz

## [0.3.4] — 2026-06-05
### Fixed
- Dateikonflikt: die NEUE Datei bekommt den Zeitstempel (Video_20260605_165031.mp4), die bestehende Datei bleibt unverändert — Tags/Plattform-Metadaten der Originaldatei bleiben erhalten

## [0.3.3] — 2026-06-05
### Fixed
- Dateikonflikt: --force-overwrites entfernt (hatte die Datei überschrieben bevor Umbenennung möglich war)
- Neues Verhalten: yt-dlp meldet "already downloaded" → bestehende Datei wird mit Zeitstempel umbenannt → Download startet automatisch erneut → beide Dateien bleiben erhalten

## [0.3.2] — 2026-06-05
### Improved
- Custom-Tag-Popup zeigt alle bereits verwendeten Tags als Schnellauswahl-Buttons (gelb), analog zu den Plattform-Buttons im Platform-Picker
- Aktiver Tag wird hervorgehoben; Trennlinie vor dem Texteingabefeld

## [0.3.1] — 2026-06-05
### Fixed
- Dateikonflikt: bestehende Datei wird mit Zeitstempel-Suffix umbenannt (z.B. Video_20260605_165031.mp4) statt überschrieben; yt-dlp speichert den neuen Download unter dem Originalnamen
- Nur echte Zieldateien werden umbenannt — temporäre Streams (Video.f137.mp4) werden ignoriert
- yt-dlp Version-Vergleich: PyPI liefert 2026.3.17, yt-dlp binary 2026.03.17 — führende Nullen werden vor Vergleich normalisiert → "Bereits aktuell" wird korrekt erkannt

## [0.3.0] — 2026-06-05
### Fixed
- Dateikonflikt: yt-dlp lud Streams herunter, konnte aber die Zieldatei nicht speichern wenn ein gleichnamiger Dateiname schon existierte — behoben mit --force-overwrites

## [0.2.9] — 2026-06-05
### Fixed
- Custom-Tag-Editor: bestehender Tag wird beim Öffnen vorausgefüllt und selektiert (war leer wirkend durch fehlenden inp.select())

## [0.2.8] — 2026-06-05
### Changed
- Platform-Tag und Custom-Tag sind jetzt getrennte, unabhängige Felder pro Datei
- Platform-Tag (blau): Klick auf ＋ öffnet Plattform-Picker (YouTube, TikTok, …)
- Custom-Tag (gelb): Klick auf ＋ Tag öffnet Texteingabe für freien Tag
- Beide Tags werden gleichzeitig angezeigt; Filter-Buttons zeigen beide Typen
- Neuer API-Endpunkt `/api/file/tag/<filename>` für Custom Tags
- Meta-Datei speichert `platform` und `tag` getrennt

## [0.2.7] — 2026-06-05
### Improved
- yt-dlp Update-Button prüft zuerst PyPI auf neue Version; Update wird nur durchgeführt wenn tatsächlich eine neuere Version verfügbar ist
- Toast "Bereits aktuell: x.x.x" wenn nichts zu tun, "Aktualisiert auf x.x.x" nach echtem Update
- Versions-Cache wird nach Update invalidiert
### Fixed
- Tag-Strings (＋ Tag, ✕ Entfernen, Eigener Tag …) fehlten in Übersetzungen — jetzt in DE/EN Locale-Dateien

## [0.2.6] — 2026-06-05
### Added
- Custom Tags: freie Texteingabe im Plattform-Picker — beliebiger Tag statt nur vordefinierter Plattformen
- Custom Tags erscheinen in Gelb (Plattform-Tags bleiben Blau) zur visuellen Unterscheidung
- Plattform-Filter zeigt auch Custom Tags automatisch an

## [0.2.5] — 2026-06-05
### Fixed
- Plattform-Popover: var(--card) existiert nicht → transparenter Hintergrund, kaum lesbar; auf var(--surf)/var(--surf2) umgestellt
- Popover: stärkerer Schatten, Accent-Border, besserer Kontrast für Dark/Light-Mode

## [0.2.4] — 2026-06-05
### Added
- Plattform-Tag manuell zuweisen oder ändern: Klick auf Badge oder "＋ Tag"-Button öffnet Popover mit allen Plattformen
- "✕ Entfernen" löscht den Tag wieder
- Bestehende Dateien (ohne automatischen Tag) können so nachträglich kategorisiert werden

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
