# Changelog — HA SysWatch

## [1.5.0] - 2026-08-30

### Added
- **Button „Build-Cache freigeben“** im Speicher-Dialog (neue Route `POST /api/build/prune`, ruft `POST /build/prune` am Docker-Socket — dasselbe wie `docker builder prune -a`). Gelöscht werden nur Build-Zwischenergebnisse, Images/Container/Volumes bleiben unberührt. Das Feld „GB behalten“ entspricht `--keep-storage`. Die Aktion verlangt wie Neustart und Kill das Add-on-Passwort, läuft in einem Hintergrund-Thread und meldet danach die freigegebene Menge samt Anzahl der Einträge; die Größen werden automatisch neu berechnet.
- Neue Option `allow_build_prune` (Standard `true`) blendet den Button aus, wenn niemand über die Oberfläche aufräumen können soll.
- DOCS erklärt, warum der Build-Cache wächst: ein sich änderndes `ARG` weit oben im Dockerfile (etwa `BUILD_VERSION`) invalidiert bei jeder Versionserhöhung alle nachfolgenden Layer, und der eingebaute Docker-Builder räumt die Einträge nie von selbst auf.

## [1.4.3] - 2026-08-30

### Fixed
- Build-Cache-Größe stimmte nicht mit `docker system df` überein. 1.4.2 hatte Einträge mit `Shared`-Flag übersprungen — dadurch zeigte die Spalte Docker's *Reclaimable* statt der Gesamtgröße (165.1 GiB statt 182.1 GB). Die Gesamtgröße kommt jetzt aus dem API-Feld `BuilderSize` (Fallback: Summe aller Einträge), freigebbar ist die Gesamtgröße minus alle Einträge mit `InUse` — genau die Rechnung der CLI.
- „Freigebbar“ bei Images und Volumes folgte einer eigenen Formel (Summe der exklusiven Layer aller Images ohne Container). Jetzt ebenfalls wie `docker system df`: Gesamtgröße minus das, was benutzt wird. Gegen eine echte Host-Ausgabe geprüft, alle vier Zeilen stimmen überein.

### Added
- Jede Zeile der Docker-Aufteilung nennt Anzahl und freigebbaren Anteil; die Überschrift zeigt zusätzlich die Gesamtsumme des freigebbaren Platzes.
- Der Telegram-Speicher-Alarm listet den Build-Cache mit auf und nennt den gesamten freigebbaren Anteil.

## [1.4.2] - 2026-08-30

### Fixed
- Build-Cache im Speicher-Dialog zeigte absurde Werte (gemeldet: 169.6 GiB auf einer deutlich kleineren Platte). `GET /system/df` liefert im `BuildCache`-Array Einträge mit gesetztem `Shared`-Flag — deren Bytes gehören bereits zu einem Image- oder Container-Layer und werden dort schon gezählt. Die Summe lief über alle Einträge und hat dieselben Layer dadurch vielfach addiert. `Shared`-Einträge werden jetzt übersprungen (`docker/cli` macht in `system df` dieselbe Ausnahme). Die Docker-Gesamtsumme fällt entsprechend auf einen plausiblen Wert.

### Added
- Build-Cache-Zeile nennt jetzt zusätzlich die Anzahl der Einträge und den freigebbaren Anteil (Einträge ohne `InUse`).

## [1.4.1] - 2026-08-30

### Added
- **Dialog „Speicherplatz“** per Linksklick auf die Kachel „Speicher frei“: Datenpartition mit Balken und Quelle, Docker-Aufteilung inklusive **freigebbar** (exklusive Layer aller Images ohne Container), die **25 größten Images** mit Größe / geteiltem Anteil / Anzahl nutzender Container, die 10 größten Container und die 15 größten Volumes. Ungenutzte Images und Volumes sind gelb markiert. Neue Route `GET /api/sizes` — die Detaillisten hängen bewusst nicht am Stats-Poll.
- **Rechtsklick auf die Kachel** startet die Größenabfrage (vorher lag das auf dem Linksklick). Im Dialog erledigt das der Button „Neu berechnen“; danach pollt die Oberfläche alle 3 s bis ein neuer Zeitstempel vorliegt, der Scan darf also Minuten dauern.

### Fixed
- Kachel-Inhalte klebten oben, weil Kacheln mit Balken höher sind als die ohne. `.card` ist jetzt ein Flex-Container mit `justify-content: center` — „CPU GESAMT“ und „RAM GENUTZT“ sitzen wieder mittig.

## [1.4.0] - 2026-08-30

### Added
- **Kachel „Speicher frei“**: freier Platz der HA-Datenpartition, Balken zeigt die Belegung (gleiche Farbskala wie SYS CPU/RAM). Werte kommen von der Supervisor-API (`/host/info`), Fallback `statvfs` auf `/config`, `/data`, `/`. Der Tooltip listet die Docker-Aufteilung (Images / Container / Volumes / Build-Cache) samt Zeitstempel; ein Klick startet die Größenabfrage sofort neu (`POST /api/sizes/refresh`).
- **Spalte „Größe“** in der Container-Tabelle (sortierbar): `SizeRw`, also die beschreibbare Schicht des Containers. Tooltip nennt zusätzlich `SizeRootFs` inkl. Image-Layer. Datenquelle ist `docker system df` — die Abfrage scannt das Dateisystem und läuft deshalb in einem eigenen Hintergrund-Thread, Intervall über die neue Option `size_interval` (Standard 15 Minuten, 0 = aus).
- **Speicher-Alarm** über die neue Option `notify_disk_threshold` (% belegt, 0 = aus). Die Telegram-Nachricht nennt Belegung, freien Platz, die Docker-Aufteilung und die fünf größten Container-Schichten — also direkt die Kandidaten, die die Platte volllaufen lassen. Auslöse- und Entwarnungsverzögerung teilen sich die bestehenden Optionen `notify_over_duration` / `notify_clear_duration`.

### Changed
- Übersichts-Kacheln kompakter (Raster ab 94 px statt 110 px, kleinere Schrift und Balken), damit die siebte Kachel in dieselbe Reihe passt. Tabellen-Padding von 10 px auf 8 px reduziert, `name-cell` von 180 px auf 170 px — die neue Spalte passt ohne zusätzliches Horizontal-Scrolling.

### Note
- Docker-**Logfiles** zählen nicht zu `SizeRw`. Ein Container kann die Platte also über sein Log füllen, ohne in der Größen-Spalte aufzufallen. Dagegen hilft nur ein Log-Limit im Docker-Daemon des Hosts (`max-size` / `max-file`) — das kann ein Add-on nicht setzen. Der Speicher-Alarm schlägt aber unabhängig von der Ursache an.

## [1.3.1] - 2026-08-22

### Fixed
- NET I/O zeigte für Container im Host-Netzwerk (`network_mode: host`, z. B. `homeassistant`) dauerhaft `0 B / 0 B`. Solche Container haben keinen eigenen Netz-Namespace, Docker liefert im Stats-Endpoint gar keinen `networks`-Block. Statt einer irreführenden 0 zeigt die Tabelle jetzt `-` mit Tooltip-Erklärung (DE/EN).

## [1.3.0] - 2026-08-12

### Added
- 24h-CPU-Verlauf pro Container: Klick auf die Mini-Sparkline in der Tabelle öffnet den bestehenden Chart-Modal (wie bei SYS CPU/RAM) mit dem Minuten-Verlauf der letzten 24h. Backend speichert dafür pro Container minütliche CPU-Durchschnitte in einer neuen SQLite-Tabelle (`container_history`), neue Route `/api/containers/<name>/history`.

### Fixed
- `_supervisor_addon_slug()` erkannte HA-Add-on-Container nur am Präfix `addon_`. HA Supervisor benennt Add-on-Container inzwischen teils mit `app_`-Präfix — Slug-Matching strippt jetzt beide Präfixe.

## [1.2.13] - 2026-07-31
- map: `addon_config` → `app_config` (Home-Assistant-Supervisor hat `addon_config` seit 2026.07 als Legacy-Name markiert, neuer Name ist `app_config`).

## [1.2.12.1] - 2026-07-13

chore(deps): bump docker from 7.1.0 to 7.2.0 in /syswatch


## [1.2.12] - 2026-07-09

### Fixed
- Add-on beendete sich bei jedem Stop/Update mit Exit-Code 137 (SIGKILL statt sauberem Stop). Ursache: `Dockerfile` basiert auf reinem `python:3.14-alpine` ohne eigenes Init-System, `run.sh` macht den Flask-Prozess per `exec` zu PID 1 — ohne eigenen Signal-Handler ignoriert der Kernel bei PID 1 unbehandelte Signale wie SIGTERM, der Supervisor musste nach Timeout hart killen. `init: false` → `init: true` in `config.yaml` (HA Supervisor stellt jetzt ein Mini-Init als echte PID 1) plus eigener `SIGTERM`-Handler in `app.py` (`os._exit(0)` — alle Hintergrund-Threads sind daemon, DB-Schreibzugriffe committen bereits pro Verbindung, kein Cleanup nötig).

## [1.2.11] - 2026-06-09

### Added
- `webui`-Feld in config.yaml: HA zeigt jetzt den Button „Benutzeroberfläche öffnen" — passt sich automatisch an den konfigurierten Host-Port an

## [1.2.10] - 2026-06-09

### Fixed
- Stop-Button: HA Add-ons werden jetzt über die Supervisor API gestoppt (`POST /addons/{slug}/stop`) statt direkt über Docker — verhindert, dass der Watchdog den Container sofort neu startet
- Reguläre Docker-Container (kein Supervisor-Eintrag) weiterhin über Docker-Socket gestoppt

## [1.2.9] - 2026-06-09

### Fixed
- Kern-Temperaturen im Footer (Core 0–N): nur „Package"-Sensoren sind klickbar (History in DB vorhanden); individuelle Kerne zeigen nur den Momentwert ohne Link — verhindert, dass ein falsches Diagramm geöffnet wird

## [1.2.8] - 2026-06-09

### Changed
- Chart-Diagramme: Aktueller Wert (z.B. „9.9%") wird jetzt oben rechts *über* dem Datenbereich angezeigt — kein Überlappen mit der Linie mehr
- Chart-Footer: Min / Avg / Max der letzten 24h werden für alle drei Charts (CPU, RAM, Temperatur) farbkodiert unterhalb des Diagramms angezeigt

## [1.2.7] - 2026-06-09

### Fixed
- `mobile-web-app-capable` Meta-Tag ergänzt (Deprecation-Warnung im Browser behoben)

## [1.2.6.1] - 2026-06-08

### Dependencies
- Dependabot: Abhaengigkeiten aktualisiert

## [1.2.6] - 2026-06-08

### Fixed
- Idle-Modus: Host-CPU/RAM wird jetzt alle 10s gemessen (statt alle 60s) — Schwellenwert-Prüfung und History-Aufzeichnung laufen damit auch im Idle-Modus zeitnah
- Idle-Modus: Container-Scan weiterhin alle 60s; sysinfo-Update zwischen den Scans ohne zweiten `_read_sysinfo()`-Aufruf in `_collect_once()`
- JS: `_pollActive` vor der `init`-IIFE deklariert (`let` temporal dead zone → `ReferenceError: Cannot access '_pollActive' before initialization`)

## [1.2.5] - 2026-06-08

### Security
- Open Redirect: `request.referrer` in `set_lang()` via `urlparse` validiert — nur relative Pfade erlaubt (CodeQL MEDIUM #130)

## [1.2.4] - 2026-06-08

### Security
- Cookie Injection: `cookie_lang` aus Literal statt URL-Parameter in `set_lang()` (CodeQL MEDIUM #49)

## [1.2.3] - 2026-06-08

### Security
- Information Exposure: Exception-Details (`str(e)`) nicht mehr in HTTP-Responses zurückgegeben; stattdessen generische `'internal error'`-Meldung + internes `log.exception()` (CodeQL #12, #15–#18)

## [1.2.2] - 2026-06-07

### Security
- XSS / Incomplete escaping: `safeJsArg()`-Hilfsfunktion hinzugefügt; Sensor-Label im History-Footer nutzt jetzt `safeJsArg()` statt manueller `replace(/'/g)` (CodeQL: js/incomplete-html-attribute-sanitization #76)

---

## [1.2.1] - 2026-06-07
### Added
- Disconnect-Erkennung: `visibilitychange` (Tab/Laptop-Aufklappen), `online`/`offline`-Events, `navigator.onLine`-Check beim Start
- Offline-Banner: abdunkelndes Overlay mit animiertem 📡, lokalisierten Texten (DE/EN) und „Neu laden"-Button
- SysWatch-spezifisch: `longPoll()` AbortError wird korrekt ignoriert — nur echte Netzwerkfehler zählen zum Fehler-Zähler

## [1.2.0] - 2026-06-06
### Added
- In-App Console: Doppelklick auf „HA SysWatch" öffnet draggbares Floating-Window mit Backend-Logs (Docker/Supervisor-Events)
### Fixed
- 24h-Verlaufscharts für CPU, RAM und Temperatur werden jetzt auch im Idle-Modus korrekt befüllt
- Telegram-Benachrichtigungen (Container-Stop/CPU/RAM-Alarm) werden jetzt auch im Idle-Modus ausgelöst
- Zeitachse im Chart: Labels aus tatsächlichem Datenbereich berechnet, aktuelle Uhrzeit am rechten Rand
- Chart-Linienstärke reduziert (2.5px → 1px) für bessere Lesbarkeit bei 1440 Datenpunkten

## [1.1.6] - 2026-06-06

- fix: Chart-Linie von 2.5px auf 1px reduziert — bei 1440 Datenpunkten überlappten die Segmente stark

## [1.1.5] - 2026-06-06
- Fix: DEBUG-Logs in Console sichtbar — Root-StreamHandler auf INFO, Root-Logger auf DEBUG; _buf_h (DEBUG) erfasst alle Level ohne HA-Log zu überschwemmen

## [1.1.4] - 2026-06-06
- Fix: Crash beim Start — Flask-Endpoint api_logs kollidierte mit vorhandener /api/container/<name>/logs Funktion; umbenannt in api_console_logs

## [1.1.3] - 2026-06-06
- Neu: In-App Console (Doppelklick auf "HA SysWatch") — draggbares Floating-Window; Python _BufferHandler erfasst alle Log-Aufrufe inkl. Docker/Supervisor-Events; GET /api/logs?since=; localStorage-Persistenz

## [1.1.2] - 2026-06-05

### Fixed
- Im Idle-Modus wurden keine Telegram-Benachrichtigungen ausgelöst — `_check_container_changes()` und `_check_thresholds()` werden jetzt auch im Idle-Zweig aufgerufen

## [1.1.1] - 2026-06-05

### Fixed
- Im Idle-Modus (kein Browser aktiv) wurden keine CPU/RAM/Temp-Daten in die History-DB geschrieben — `_tick_history()` wird jetzt auch nach der Idle-Sammlung aufgerufen (alle 60s)
- Zeitachse im Chart: Labels werden jetzt aus dem tatsächlichen Datenbereich berechnet (step 1/2/3/4/6h je nach Fenstergröße) — zeigt immer sinnvolle Markierungen auch bei kurzem Datenfenster
- Aktuelle Uhrzeit (`HH:MM`) erscheint am rechten Rand der Zeitachse

## [1.1.0] - 2026-06-05

### Stable Release
- README und DOCS.md vollständig überarbeitet und auf aktuellen Stand gebracht
- Alle Features seit v1.0.0 dokumentiert: 24h-Charts, Temperatur, Verlaufs-DB, Telegram-Erweiterungen, Balken-Kacheln, Port-Links, HA-Status-Kachel

### Enthaltene Features (seit v1.0.0)
- SYS CPU / SYS RAM Kacheln mit Farbbalken (klickbar → 24h-Chart)
- 24h-Verlaufscharts für CPU, RAM und Temperatur (SQLite, restart-sicher)
- CPU-Temperatur (Package + alle Kerne) aus coretemp/k10temp hwmon
- Temperatur-Chart mit Schwellenwert-Referenzlinien + ← Zurück-Button
- Telegram: Inline-Keyboard ▶ Starten, Top-5-Verbraucher in Alerts (RAM: GiB + %), Chat-ID-Autoerkennung, 📨 Test-Button, Startup-Benachrichtigung
- Port-Übersicht mit klickbaren Links (Host-IP aus Supervisor Netzwerk-API)
- HA-Status-Kachel (Supervisor/Support/Health) + Footer-Versionen
- Alle UI-Strings vollständig in DE/EN übersetzt

## [1.0.25] - 2026-06-05

### Added
- Zurück-Button (←) im Temperatur-Chart-Header: navigiert direkt zurück zum SYS CPU Chart

## [1.0.24] - 2026-06-05

### Changed
- Temperatur-Rotschwelle von 85°C auf 90°C angehoben (grün <60, gelb <75, orange <90, rot ≥90)

## [1.0.23] - 2026-06-05

### Fixed
- Alle Chart-bezogenen Strings aus locales/de.json + en.json ergänzt (hist_title_*, hist_no_data, hist_load_error, hist_no_sensors, hist_temp_tooltip, hist_open_cpu/ram)
- JS nutzt jetzt T.-Referenzen statt hart-kodierter deutscher Texte

## [1.0.22] - 2026-06-05

### Fixed
- Temperatur-Chart-Titel zeigt jetzt den Sensor-Namen: "CPU Temperatur (Package id 0) — Verlauf 24h"

## [1.0.21] - 2026-06-05

### Fixed
- History-DB Lesefehler "tuple index out of range": SELECT-Query fehlte `temp`-Spalte

## [1.0.20] - 2026-06-05

### Added
- CPU-Temperaturverlauf wird in SQLite gespeichert (`temp`-Spalte, Migration automatisch)
- Klick auf Temperaturwerte im CPU-Chart-Footer öffnet Temperatur-Verlaufsdiagramm (24h)
- Temperatur-Chart: Y-Achse in °C, farbige gestrichelte Schwellenwert-Linien bei 60/75/85°C, Linie farbkodiert nach Temperaturbereich

## [1.0.19] - 2026-06-05

### Fixed
- Chart-Lesbarkeit: sysPctColor() und tempColor() geben jetzt Hex-Farben zurück statt CSS-Variablen (die im Canvas-Kontext nicht aufgelöst werden)
- Area-Fill nutzt die Durchschnitts-Farbe der Daten (grün/gelb/orange/rot) mit 33% Deckkraft oben — klar sichtbar
- Linie dicker (2.5px statt 2px), Grid-Linien und Y-Achsenbeschriftungen kontrastreicher

## [1.0.18] - 2026-06-05

### Changed
- CPU-Temp liest jetzt bevorzugt `coretemp`/`k10temp` hwmon (Package temp1) statt ACPI-Zone — genauere Intel/AMD-Werte
- Alle Kern-Temperaturen (Package + Core 0–N) werden im CPU-Chart-Footer angezeigt, farbkodiert (grün/gelb/orange/rot)
- Lüfter werden nur angezeigt wenn tatsächlich hwmon-Daten vorhanden; kein Fallback-Text mehr wenn nur Temp verfügbar
- `core_temps` in `api_stats()` ergänzt

## [1.0.17] - 2026-06-05

### Added
- **24h-Verlaufschart**: Klick auf SYS CPU / SYS RAM Kachel öffnet Canvas-Diagramm mit 24h-Verlauf
- SQLite-DB `/config/syswatch_history.db` — überlebt Neustarts; 1-Minuten-Durchschnittswerte, max. 1440 Einträge (24h)
- API `GET /api/sysinfo/history` liefert alle gespeicherten Punkte
- Farbkodierte Linie im Chart (grün/gelb/orange/rot) + Area-Fill + Zeitachse + aktueller Wert als Dot
- CPU-Temp aus `/sys/class/thermal/` + Lüfter-RPM aus `/sys/class/hwmon/` — werden im CPU-Chart als Footer angezeigt
- `cpu_temp` + `fans` in `api_stats()` (5s gecacht)

## [1.0.16] - 2026-06-05

### Changed
- SYS CPU und SYS RAM Kacheln: Prozentzahl ersetzt durch Balken (grün ≤70%, gelb >70%, orange >80%, rot >90%), Prozentwert als kleine Zahl darunter

## [1.0.15] - 2026-06-05

### Changed
- Top-5-RAM-Zeilen zeigen jetzt Größe + Prozent: `1.2 GiB (18.4%)` statt nur `18.4%`

## [1.0.14] - 2026-06-05

### Added
- CPU/RAM-Alarmbenachrichtigungen enthalten jetzt die Top 5 Verbraucher (Name + Wert%)
- 📨 Test-Button neben dem Logo (nur Desktop ≥620px): sendet sofort eine Test-Telegram-Nachricht mit aktuellen Top-5-CPU und Top-5-RAM Werten

## [1.0.13] - 2026-06-05

### Fixed
- Telegram ▶ Starten schlug mit "Container nicht gefunden" fehl: Docker-Containernamen beginnen mit `addon_`, Supervisor-Slugs nicht — `_supervisor_addon_slug()` strippt jetzt das Prefix vor dem Vergleich

## [1.0.12] - 2026-06-05

### Changed
- `telegram_chat_id` ist jetzt optional: SysWatch erkennt die Chat-ID automatisch wenn der Bot angeschrieben wird (`/start`) und sendet eine Bestätigung
- Token leer → Polling-Thread schweigt (kein Log-Spam); loggt erst wenn Token gesetzt wird
- Callback-Sicherheit: ohne konfigurierte Chat-ID wird erste Kontaktaufnahme akzeptiert und Chat-ID gesetzt; danach nur noch diese Chat-ID

## [1.0.11] - 2026-06-05

### Added
- Telegram Inline-Keyboard-Callback: Stop-Nachricht enthält ▶ Starten-Button
- Hintergrund-Thread `telegram-polling` empfängt Callbacks via `getUpdates` Long-Polling
- Klick auf ▶ Starten → startet Container (Docker / Supervisor-Fallback), editiert Nachricht sofort auf "⏳ Startbefehl gesendet…"
- Wenn Container wieder läuft → Nachricht wird auf ✅ Container läuft wieder editiert, Button entfernt
- Nur konfigurierte `telegram_chat_id` kann Callbacks auslösen (Sicherheit)
- `api_start()` auf `_start_container_core()` refaktoriert (gemeinsame Logik mit Callback-Handler)

## [1.0.10] - 2026-06-05

### Added
- Telegram-Log: jede ausgehende Nachricht erscheint im HA-Log mit Vorschau (`[Telegram] →`) und Bestätigung (`[Telegram] Gesendet.`) oder Fehler
- Startup-Benachrichtigung: nach dem ersten abgeschlossenen Zyklus sendet SysWatch einmalig Datum/Uhrzeit, HA-/Supervisor-/OS-Version, Anzahl laufender und gestoppter Container sowie Host-IP

## [1.0.9] - 2026-06-05

### Added
- `notify_over_duration` (Sek., Standard 0): CPU/RAM muss diese Zeit dauerhaft über Schwellenwert liegen bevor Alarm ausgelöst wird
- `notify_clear_duration` (Sek., Standard 120): CPU/RAM muss diese Zeit dauerhaft unter Schwellenwert liegen bevor Entwarnung gesendet wird
- Translations DE/EN für beide neuen Optionen

## [1.0.8] - 2026-06-05

### Changed
- Container-Stop/Start-Notification umgebaut auf State-Tracking (Option A):
  Nur unerwartete Stops/Starts lösen Telegram aus — eigene SysWatch-Aktionen (Stop/Kill/Start-Button) werden als "manuell" markiert und unterdrückt (90s TTL)
- Keine Notification mehr bei manuellem Stop/Kill über SysWatch-UI
- 💥 bei unerwartetem Stop, ▶️ bei unerwartetem Start, ✅ CPU/RAM-Entwarnung nach 2 Min.

## [1.0.7] - 2026-06-05

### Added
- Telegram-Benachrichtigungen: Bot Token + Chat ID als Config-Optionen
- Alarm bei Container-Stop/Kill: 🛑/💀 Nachricht mit Container-Name
- Alarm bei CPU-Überschreitung: ⚠️ Nachricht + ✅ Entwarnung nach 2 Min. unter Schwellenwert (10 Min. Cooldown)
- Alarm bei RAM-Überschreitung: gleiche Logik
- Neue Config-Optionen: `telegram_bot_token`, `telegram_chat_id`, `notify_cpu_threshold`, `notify_ram_threshold` (0 = deaktiviert)

## [1.0.6] - 2026-06-04
- fix: Log-Zeitstempel vollständig in allen Ausgaben (force=True / UVICORN_LOG_CONFIG)

## [1.0.5] - 2026-06-04
- Log-Ausgaben mit Datum und Uhrzeit: `[INFO] [YYYY-MM-DD HH:MM:SS] Nachricht`

## [1.0.4] - 2026-06-04

### Added
- Port-Übersicht: Host-Ports sind jetzt klickbare Links (`http://<host-ip>:<port>`) — Host-IP wird aus `/network/info` Supervisor API gelesen (erster verbundener Interface)
- Fallback: ohne Host-IP bleibt Port-Nummer als Text sichtbar

## [1.0.3] - 2026-06-04

### Added
- Footer zeigt HA Core-, Supervisor- und OS-Version (via Supervisor API, 3 parallele Calls, 60s Cache)

## [1.0.2] - 2026-06-04

### Changed
- Kacheln "Container" und "Laufend" zusammengeführt — zeigt laufende Container mit Gesamtanzahl als Sub-Label
- Neue Kachel "HA Status" (ganz links): zeigt Supervisor/Support/Health-Status aus der Supervisor API; grün = alles OK, gelb = unsupported, rot = disconnected/unhealthy; 30s Cache

## [1.0.1] - 2026-06-04

### Added
- `verbose_log` Option (Standard: `false`) — unterdrückt die pro-Zyklus-Logs (Docker-Socket, Abfrage-Statistik, Supervisor-Add-ons). Nur Modus-Wechsel, Fehler und Aktionen bleiben immer sichtbar.

## [1.0.0] - 2026-06-04

### Stable Release
- Erstes stabiles Release nach ausgiebigem Testen
- Alle bekannten Bugs behoben, Feature-Set vollständig

## [0.4.0] - 2026-06-02

### Fixed
- Stop-Button war verzerrt (&#9646; Rechteck-Zeichen + asymmetrisches Padding) → SVG-Quadrat-Icon
- Totenkopf-Icon war bei 13px kaum erkennbar → ersetzt durch Power-Off-SVG (klarer Kontrast)
- Restart-Button: ↺ Unicode → SVG für konsistente Darstellung
- Start-Button: ▶ Unicode → SVG
- Neue CSS-Klasse `.act-icon` für gleichmäßiges Padding bei Icon-only-Buttons

## [0.3.9] - 2026-06-02

### Added
- Haupttabelle merkt sich Sortierung (Spalte + Richtung) in localStorage — bleibt nach Reload erhalten
- Port-Übersicht: alle Spalten sortierbar (Name, Host-Port, Container-Port, Protokoll) mit Pfeil-Indikator

## [0.3.8] - 2026-06-02

### Fixed
- Start-Button für gestoppte HA Add-ons schlug mit 404 fehl — Docker-Container wurde von HA entfernt. Fix: Docker-Versuch → bei NotFound Fallback auf Supervisor API (`/addons/{slug}/start`)

## [0.3.7] - 2026-06-02

### Fixed
- Port-Duplikate entfernt: Docker meldet IPv4 (0.0.0.0) und IPv6 (::) als separate Bindings — Deduplizierung per (host, container, proto)-Key im Backend
- "Keine Host-Port-Mappings"-Label war immer sichtbar (fehlende `.hidden`-CSS-Klasse) — auf `style.display` umgestellt

### Added
- Suchfeld im Port-Übersicht-Modal (filtert nach Container-Name oder Port-Nummer)

## [0.3.6] - 2026-06-02

### Added
- Port-Übersicht: "Ports"-Button in der Controls-Zeile öffnet Modal mit allen Host-Port-Mappings (Container | Host-Port | Container-Port | Protokoll), sortiert nach Name und Port-Nummer
- Backend: `ports_mapped`-Feld pro Container aus `container.ports` (kein Extra-API-Call)

## [0.3.5] - 2026-06-02

### Changed
- Sprach-Buttons (DE/EN) auf mobilen Geräten (≤620px) ausgeblendet — Sprache wird automatisch über Browsersprache erkannt

## [0.3.4] - 2026-06-02

### Fixed
- `hassio_role: manager` ergänzt — `hassio_api: true` allein reicht nicht für den `/addons`-Endpoint, HA lieferte 403

## [0.3.3] - 2026-06-02

### Fixed
- `hassio_api: true` in config.yaml ergänzt — ohne diese Berechtigung blockt HA den Supervisor-API-Aufruf für gestoppte Add-ons
- Logging in `_get_supervisor_stopped_addons()` verbessert: Token-Fehler und API-Fehler werden jetzt sichtbar geloggt

## [0.3.2] - 2026-06-02

### Removed
- PWA-Installationsbanner entfernt — erschien nach jedem Reload; Browser-eigenes Installationssymbol reicht aus. Service Worker bleibt aktiv.

## [0.3.1] - 2026-06-02

### Fixed
- Gestoppte HA Add-ons nicht sichtbar: HA entfernt gestoppte Add-on-Container vollständig aus Docker — `containers.list(all=True)` findet sie deshalb nicht. Fix: nach Docker-Abfrage werden gestoppte Add-ons zusätzlich über die Supervisor API geholt und zum Ergebnis hinzugefügt (Duplikate werden per Name ausgeschlossen)
- SW-Cache-Name auf `syswatch-v2` erhöht — erzwingt vollständige Browser-Cache-Invalidierung
- Default `show_stopped` in config.yaml auf `true` geändert (sinnvollerer Standard)

## [0.3.0] - 2026-06-02

### Added
- Start/Stop-Buttons pro Container: ▶ (grün) bei gestoppten Containern, ■ (rot) bei laufenden — mit Passwortbestätigung über dasselbe Modal wie Restart/Kill
- Backend-Endpoints `/api/container/<name>/start` und `/api/container/<name>/stop` (POST, Passwort-geschützt)
- Übersetzungen für Start/Stop in `de.json` und `en.json`

## [0.2.9] - 2026-06-02

### Fixed
- `show_stopped`-Config hatte keine Wirkung — Config-Default wird jetzt via Template an den Client übergeben (`CFG_SHOW_STOPPED`) und initialisiert die Checkbox beim Laden. Manuelle Benutzerauswahl wird in localStorage gespeichert (Vorrang vor Config-Default) und bleibt nach Reload erhalten.

## [0.2.8] - 2026-06-01

### Fixed
- Idle-Abfrage (2 Worker, bis zu 47s für 48 Container) wurde beim Resume nicht unterbrochen — `_collect_once()` erhält jetzt ein Abort-Event im Idle-Modus; nach dem nächsten fertiggestellten Container wird die Sammlung sofort abgebrochen und der Aktiv-Zyklus startet unverzüglich

## [0.2.7] - 2026-06-01

### Fixed
- 60s Idle-Sleep wurde beim Resume nicht unterbrochen wenn der Long-Poll bereits vor dem Heartbeat verbunden war — `_is_viewer_active()` gab durch `has_sse=True` fälschlicherweise "aktiv" zurück und verhinderte `_collect_event.set()`. Fix: `was_idle` wird jetzt direkt aus `_collector_mode` gelesen

## [0.2.6] - 2026-06-01

### Fixed
- Chrome-Credential-Autofill im Suchfeld: versteckte Dummy-Inputs als Autofill-Trap + `autocomplete="new-password"` am Suchfeld (Chrome ignoriert `off` seit v34)

## [0.2.5] - 2026-06-01

### Fixed
- Status-Dot blieb nach Resume gelb bis zum nächsten Collector-Zyklus — `_collector_mode` wird jetzt sofort auf `active` gesetzt wenn Viewer-API oder Heartbeat den Wechsel auslöst

## [0.2.4] - 2026-06-01

### Fixed
- Chrome zeigte Passwort-Autofill im Suchfeld — `autocomplete="off"` gesetzt

## [0.2.3] - 2026-06-01

### Fixed
- Log-Meldung "Kein Browser aktiv" erschien fälschlicherweise auch wenn der User bewusst Pause gedrückt hat — `_viewer_paused`-Flag eingeführt, Collector unterscheidet jetzt zwischen "Browser pausiert" und "kein Browser verbunden"

## [0.2.2] - 2026-06-01

### Fixed
- Alle Action-Buttons (Logs, Restart, Kill) reagierten nicht — veralteter `connectSSE()`-Aufruf in `init()` warf ReferenceError und verhinderte die Registrierung des Click-Handlers

## [0.2.0] - 2026-06-01

### Fixed
- Browser-Timer feuerte gelegentlich bevor neue Daten bereit waren — cycle_s Buffer von 0.3s auf 1.0s erhöht

## [0.1.9] - 2026-06-01

### Added
- `translations/en.yaml` und `translations/de.yaml` mit Beschreibungen aller Optionen (erscheinen jetzt in der HA Add-on UI)
- README.md und DOCS.md mit Performance-Tuning-Tabelle, Erklärungen zu collect_interval/collect_workers/viewer_timeout

## [0.1.8] - 2026-06-01

### Changed
- Interval-Dropdown entfernt — Browser kalibriert sich automatisch auf `cycle_s` (Abfragezeit + Sleep + Buffer) aus der Stats-Response
- Header zeigt statisch "~5.5s" (tatsächlicher Zyklus) statt konfigurierbarem Dropdown
- Backend gibt `cycle_s` in Stats-Response zurück

## [0.1.7] - 2026-06-01

### Fixed
- Auto-Refresh funktionierte nicht (SSE wurde durch Flask-Buffering verzögert) — ersetzt durch Long-Polling: Browser hält /api/wait offen, Server antwortet sofort nach jeder abgeschlossenen Docker-Abfrage; kein Proxy/Buffering-Problem möglich

## [0.1.6] - 2026-06-01

### Changed
- `collect_workers` Maximum von 32 auf 64 erhöht

## [0.1.5] - 2026-06-01

### Changed
- `viewer_timeout` als konfigurierbare Add-on-Option (Standard: 180s, Min: 30s, Max: 1800s / 30min)

## [0.1.4] - 2026-06-01

### Added
- SSE (Server-Sent Events): Browser bekommt sofort nach jeder Docker-Abfrage ein Push-Event und fetcht neue Daten — kein festes Polling-Interval mehr nötig; Timer bleibt als Fallback
- `/api/viewer` Endpoint: Pause/Resume-Button sendet sofort Signal ans Backend (Logausgabe, sofortiger Modus-Wechsel ohne 30s Wartezeit)
- Farbiger Modus-Dot im Header (grün=aktiv, gelb=idle, rot=pausiert)
- Pause-Button zeigt jetzt klar gelben Rand + Pause-Icon bei manuellem Pause, gedimmten Rand wenn Backend im IDLE-Modus

### Fixed
- Pause-Button-Klick war visuell unsichtbar — CSS-Klassen-Ansatz statt opacity-Manipulation

## [0.1.3] - 2026-06-01

### Fixed
- Collector startete beim Add-on-Start sofort im IDLE-Modus (60s Pause zwischen Abfragen), weil `_viewer_last_seen = 0.0` → wird jetzt auf `time.time()` initialisiert, Startup gilt als "aktiv"
- Heartbeat konnte den Collector nicht aus dem IDLE-Sleep aufwecken → `threading.Event` ersetzt `time.sleep`, Heartbeat weckt sofort auf

## [0.1.2] - 2026-06-01

### Added
- Startup-Banner im Log: Version, collect_interval, collect_workers, session_hours, Docker-Socket-Pfade
- Collector-Log pro Zyklus: Anzahl Container, laufende Container, Worker, Abfragedauer
- Modus-Wechsel-Log: IDLE→AKTIV und AKTIV→IDLE mit Grund und konfigurierten Werten
- Heartbeat-Log bei Übergang IDLE→AKTIV (IP-Adresse des Browsers)
- Abmeldungs-Log (Logout)

## [0.1.1] - 2026-06-01

### Added
- Performance-Mode: Browser sendet alle 10s einen Heartbeat; kein Heartbeat seit 30s → Backend wechselt automatisch in Idle-Modus (2 Worker, 60s Interval)
- Pause-Button (⚡/⏸) im Header zum manuellen Pausieren der Datenerfassung
- Visibility API: Heartbeat stoppt automatisch wenn Tab nicht sichtbar, nimmt bei Rückkehr sofort wieder auf
- Zustand wird in localStorage gespeichert

## [0.1.0] - 2026-06-01

### Added
- Kill-Button (Totenkopf-Icon) pro Container — sendet SIGKILL, erfordert Passwortbestätigung
- `collect_interval` (Standard: 3s) und `collect_workers` (Standard: 16, Min: 4, Max: 32) als konfigurierbare Add-on-Optionen

### Changed
- `refresh_interval` aus den Add-on-Optionen entfernt — UI-Dropdown (Standard 5s) reicht
- Browser-Standard-Refresh-Intervall auf 5s gesetzt

## [0.0.9] - 2026-06-01

### Fixed
- Paralleles Abfragen erhöhte CPU-Last spürbar — MAX_WORKERS auf 16 begrenzt, COLLECT_INTERVAL auf 3s erhöht; Zyklus ~6s bei deutlich reduzierter Last

## [0.0.8] - 2026-06-01

### Fixed
- Daten aktualisierten sich nur alle 10–15s statt im eingestellten Intervall — alle Container-Abfragen laufen jetzt vollständig parallel (ein Thread pro Container statt max. 12), Collector-Interval von 5s auf 1s reduziert → Gesamtzyklus ~2s

## [0.0.7] - 2026-06-01

### Added
- SYS RAM Karte zeigt `used / total` als Sub-Label (z.B. `11.3 GiB / 31.1 GiB`), kein Hover mehr nötig

## [0.0.6] - 2026-06-01

### Added
- Light/Dark-Mode-Toggle (Mond/Sonne-Icon im Header, gespeichert in localStorage)
- Light Mode auf Login-Seite ebenfalls verfügbar
- Aktualisierungsintervall 1s hinzugefügt
- Logout-Button durch Icon ersetzt (Pfeil nach rechts), Refresh-Button als Icon

## [0.0.5] - 2026-06-01

### Fixed
- Sticky-Tabellenkopf überlagerte erste Zeile — grundlegende Ursache behoben: `overflow-x: auto` auf `.table-wrap` machte es zum Scroll-Container und brach `position: sticky`. Lösung: `body` scrollt nicht mehr, Inhalt scrollt in `#main-scroll` (`flex: 1; overflow-y: auto`), horizontaler Scroll in separatem `.table-scroll`-Wrapper, `<th>` nun `top: 0`

### Added
- Passwortbestätigung beim Container-Neustart: Modal fragt das Dashboard-Passwort ab, Server validiert vor Ausführung (HTTP 403 bei falschem Passwort)

## [0.0.4] - 2026-06-01

### Fixed
- Sticky-Tabellenkopf überlagerte erste Zeile — Header-Höhe wird jetzt dynamisch per JS berechnet (`--hdr-h` CSS-Variable) statt fest auf 44px gesetzt

### Added
- CPU-Takt aus `/proc/cpuinfo` (Ø GHz + Anzahl Kerne) als Sub-Label unter der SYS-CPU-Karte

## [0.0.3] - 2026-06-01

### Fixed
- Logs-Button funktionierte nicht — HTML-Attribut-Bug durch onclick mit JSON.stringify behoben (Event-Delegation via data-action/data-name)

### Added
- Zwei neue Summary-Karten: SYS CPU % und SYS RAM % (Systemauslastung des Hosts via /proc/stat und /proc/meminfo)

## [0.0.2] - 2026-06-01

### Fixed
- `full_access: true` durch `docker_api: true` ersetzt — mountet `/var/run/docker.sock` korrekt und zeigt Docker-Badge in der HA Add-on UI
- Docker-Socket-Suche über mehrere Pfade (`/var/run/docker.sock`, `/run/docker.sock`, `/host/...`)
- Supervisor API als Fallback wenn Docker-Socket nicht verfügbar (zeigt HA Add-ons)

## [0.0.1] - 2026-06-01

### Added
- Initial release
- Sortable table with CPU %, RAM %, NET I/O, DISK I/O, PIDs per container
- Real-time CPU sparkline history per container
- Summary cards: total containers, running, total CPU, total RAM
- Auto-refresh (5 / 10 / 30 / 60 seconds, configurable)
- Log viewer modal (last 200 lines with timestamps)
- Container restart action with confirmation dialog
- Password-protected login with brute-force lockout (5 attempts / 15 min block)
- Session management with configurable expiry
- DE / EN language support
- PWA support (installable, service worker, manifest)
- Mobile-responsive layout
- Dark theme
