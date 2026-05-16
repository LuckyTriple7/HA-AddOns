# Changelog

## [2.1.4] - 2026-05-16

### Behoben
- Base-Image auf `jlesage/baseimage-gui:debian-12-v4.12.1` aktualisiert — behebt noVNC `isAndroid`-SyntaxError (inkonsistentes noVNC-Bundle in v4.12.0)
- Fontconfig-Config (`/etc/fonts`) aus deps-Stage kopiert — behebt `Cannot load default config file`
- Locale-Daten (`de_DE.UTF-8`) aus deps-Stage übernommen — behebt GTK-Locale-Warnung

## [2.1.3] - 2026-05-16

### Behoben
- deps-Stage installiert jetzt `firefox-esr` komplett — apt löst alle transitiven Abhängigkeiten (libX11-xcb, libasound, libxkbcommon, ...) automatisch auf; kein manuelles Nachpflegen mehr nötig

## [2.1.2] - 2026-05-16

### Behoben
- `libasound2` (ALSA) und `libxkbcommon0` zur deps-Stage hinzugefügt — `libasound.so.2: cannot open shared object file`

## [2.1.1] - 2026-05-16

### Behoben
- `curl`, `jq`, `xz-utils`, `ca-certificates` wieder via apt-get installiert — diese sind NICHT vorinstalliert; nur GUI-Pakete scheitern in jlesage's Repos, nicht kleine Utilities

## [2.1.0] - 2026-05-16

### Geändert
- Multi-Stage-Build: GTK3-Libs (`libgtk-3-0`, `libdbus-glib-1-2`, `libxt6`, `libpci3`) aus `debian:bookworm-slim` holen — jlesage's Debian-Base hat keine GUI-Pakete in seinen Repos; `COPY --from=deps` kopiert die Libs ohne jlesage-eigene Dateien zu überschreiben

## [2.0.9] - 2026-05-16

### Behoben
- Debian bookworm main Repo explizit in `/etc/apt/sources.list.d/bookworm-main.list` hinzugefügt — jlesage's Base-Image hat nur minimale Repos; `ca-certificates`, `curl` etc. waren bereits vorinstalliert (deshalb kein Fehler), GUI-Pakete wie `firefox-esr` fehlten aber

## [2.0.8] - 2026-05-16

### Behoben
- Firefox-Abhängigkeiten anders gelöst: `firefox-esr` aus Debian-Repos installieren zieht alle Libraries (GTK3, DBus etc.) als Deps mit; danach `firefox-esr` Binary entfernen — Libraries bleiben erhalten, Mozilla's Build nutzt sie. Umgeht das Problem mit unsicheren Package-Namen in jlesage's Base.

## [2.0.7] - 2026-05-16

### Behoben
- `libgtk-3-0`, `libdbus-glib-1-2`, `libxt6` installiert — jlesage/baseimage-gui bringt diese Firefox-Laufzeit-Abhängigkeiten nicht mit; `libgtk-3.so.0: cannot open shared object file` war der Fehler

## [2.0.6] - 2026-05-16

### Behoben
- `USER_ID=0 GROUP_ID=0` gesetzt — jlesage startet App als UID 1000, kann aber nicht in `/data` schreiben (root-owned); wie im Original-Repo (mincka) als root ausführen

## [2.0.5] - 2026-05-16

### Neu
- Konfigurationsoptionen wie im Original-Repo: `DISPLAY_WIDTH`, `DISPLAY_HEIGHT`, `DARK_MODE`, `VNC_PASSWORD`, `KEEP_APP_RUNNING`, `TZ`, `FF_OPEN_URL`, `FF_KIOSK`, `FF_CUSTOM_ARGS`
- `cont-env.d`-Mechanismus — Optionen aus `/data/options.json` werden als ENV-Variablen gesetzt, bevor jlesage Init-Skripte laufen (Auflösung, Dunkelmodus, VNC-Passwort etc. konfigurierbar)
- Firefox startet automatisch neu bei Absturz (`KEEP_APP_RUNNING=1` Standard)
- Kiosk-Modus, Start-URL und eigene Firefox-Argumente per Option konfigurierbar

### Behoben
- Crash-Loop beim Start behoben — `08-clear-tmp-dir.sh` überschrieben: HA mounted `/tmp/run/cid` als Device, das jlesage's Original-Skript nicht entfernen kann; neues Skript räumt `/tmp` selektiv auf

## [2.0.4] - 2026-05-16

### Behoben
- `xz-utils` installiert — `tar -xJ` benötigt xz-Support der im jlesage Base Image fehlt

## [2.0.3] - 2026-05-16

### Behoben
- Firefox-Download auf `.tar.xz` umgestellt — Mozilla liefert seit Firefox 100+ kein `.tar.bz2` mehr; `tar -xJ` statt `tar -xj`
- Standard-Version auf `140.10.2esr` (aktuelle ESR) korrigiert

## [2.0.2] - 2026-05-16

### Behoben
- `curl` und `ca-certificates` wieder in apt aufgenommen — werden für Firefox-Download von Mozilla benötigt

## [2.0.1] - 2026-05-16

### Behoben
- Überflüssige apt-Pakete entfernt — jlesage Base Image bringt GUI-Libraries mit; nur `jq` wird noch installiert

## [2.0.0] - 2026-05-16

### Komplett neu aufgebaut
- Basis gewechselt auf `jlesage/baseimage-gui:debian-12-v4` — VNC, noVNC, Window Manager, Clipboard-Sync alles vom Base Image übernommen
- Firefox direkt von Mozilla geladen (immer aktuelle ESR-Version, nicht Debian-Paket)
- Nur noch amd64 (kein ARM mehr)
- `startapp.sh` statt `run.sh` — nur noch Firefox-Start + user.js, kein manuelles VNC/websockify/matchbox
- Build-Workflow ohne QEMU (deutlich schneller)

## [1.0.12] - 2026-05-16

### Behoben
- `autocutsel -fork` mit `|| true` abgesichert — Fehler beim X11-Connect verhinderte Start von websockify und Firefox (set -e)
- Sleep nach Xvnc-Start von 1s auf 3s erhöht — verhindert Race Condition wenn Xvnc noch nicht bereit ist

## [1.0.11] - 2026-05-16

### Behoben
- `ca-certificates` explizit installiert — fehlte bei `--no-install-recommends`, was curl-SSL-Fehler (exit 77) beim noVNC-Download verursachte

## [1.0.10] - 2026-05-16

### Geändert
- noVNC auf v1.7.0 aktualisiert — aktuelle stabile Version mit vollständigem `navigator.clipboard`-Support

## [1.0.9] - 2026-05-16

### Behoben
- noVNC-Version auf v1.4.0 korrigiert (v1.5.0 existiert nicht); curl-Fehler durch temporäre Datei statt Pipe sichtbar gemacht

## [1.0.8] - 2026-05-16

### Behoben
- noVNC-Download im Docker-Build schlägt nicht mehr fehl — GitHub API Rate Limit im CI umgangen; Version jetzt hardcodiert (v1.5.0) statt dynamisch per API abgefragt

## [1.0.7] - 2026-05-16

### Geändert
- noVNC-Paket aus Debian ersetzt durch neueste Version direkt von GitHub — enthält automatischen Clipboard-Sync via `navigator.clipboard` Browser API; Copy/Paste funktioniert jetzt nahtlos ohne noVNC-Panel

## [1.0.6] - 2026-05-16

### Behoben
- Fenster-Schließen-Button weiterhin sichtbar — Openbox traf Firefox ESR nicht (WM_CLASS ist `Navigator`, nicht `Firefox*`); ersetzt durch `matchbox-window-manager` der speziell für Kiosk-Betrieb gebaut ist und Fenster automatisch vollbild ohne Titelleiste öffnet
- Clipboard-Sync: `autocutsel -fork` korrekt als Daemon gestartet (ohne `-fork` lief er im Vordergrund und blockierte)

## [1.0.5] - 2026-05-16

### Neu
- Clipboard-Sync: `autocutsel` synchronisiert X11 CLIPBOARD ↔ PRIMARY ↔ VNC — Copy/Paste zwischen Host-Browser und Firefox funktioniert jetzt

### Behoben
- Firefox-Fenster hatte Schließen-Button sichtbar — Openbox-Konfiguration entfernt Fensterrahmen für Firefox-Fenster und maximiert es automatisch

## [1.0.4] - 2026-05-16

### Neu
- Downloads werden in `/share/firefox` gespeichert — persistentes HA-Shared-Verzeichnis, für alle Add-ons zugänglich

### Behoben
- Firefox-Menüs und Popups verschwanden bei Mausbewegung — Openbox Window Manager hinzugefügt; ohne WM verlor Firefox den Fokus bei VNC-Maus-Events

## [1.0.3] - 2026-05-16

### Geändert
- Xvfb + x11vnc durch TigerVNC (`Xvnc`) ersetzt — virtuelles Display und VNC-Server in einem; unterstützt `resize=remote` für dynamische Auflösungsanpassung an das Browser-Fenster
- noVNC-Parameter von `resize=scale` auf `resize=remote` geändert — Firefox füllt jetzt das Fenster ohne schwarze Ränder

## [1.0.2] - 2026-05-16

### Behoben
- WebSocket-Verbindung schlug fehl ("Failed to connect to server") — noVNC baute die WebSocket-URL ohne den HA-Ingress-Pfad-Prefix (`/api/hassio_ingress/TOKEN/`) und landete so bei HA statt beim Add-on; der Pfad wird jetzt dynamisch aus der aktuellen URL berechnet und via `path=`-Parameter an noVNC übergeben

## [1.0.1] - 2026-05-16

### Behoben
- noVNC verbindet sich jetzt automatisch (`autoconnect=true`) — kein manueller Klick auf „Verbinden" mehr nötig
- Locale `de_DE.UTF-8` wird nun korrekt im Image generiert (locale-gen + update-locale)
- DBus-Session wird vor Firefox-Start initialisiert (`dbus-launch`) — behebt Gtk-WARNING
- Pakete `libpci3`, `libegl1`, `libgl1-mesa-dri`, `libdbus-glib-1-2` ergänzt — behebt glxtest-Warnungen
- Software-Rendering explizit in `user.js` aktiviert (`layers.acceleration.disabled`, `gfx.webrender.all`)

## [1.0.0] - 2026-05-16

### Erstveröffentlichung

- Firefox ESR direkt in der HA-Seitenleiste via noVNC (kein externer VNC-Client nötig)
- Eigenes Docker-Image auf Basis von `debian:bookworm-slim` — kein jlesage/docker-firefox als Abhängigkeit
- Deutsche Sprache voreingestellt (`firefox-esr-l10n-de`, `intl.locale.requested = de`)
- Persistentes Firefox-Profil in `/data/profile` — überdauert Neustarts und Updates
- Option `memory_limit_mb` — begrenzt Firefox-RAM-Verbrauch via `user.js`
- Automatische Updates via GitHub Actions (prüft täglich Firefox ESR über Mozilla API)
- Inspiriert von [mincka/ha-addons/firefox](https://github.com/mincka/ha-addons/tree/main/firefox)
