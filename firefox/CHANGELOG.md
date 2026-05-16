# Changelog

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
