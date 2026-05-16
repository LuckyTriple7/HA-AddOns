# Changelog

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
