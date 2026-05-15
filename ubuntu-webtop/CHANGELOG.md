# Changelog

## [1.4.3] - 2026-05-15
### Hinzugefügt
- LibreOffice (Writer, Calc, Impress) mit deutscher Sprachunterstützung und Hilfe

## [1.4.2] - 2026-05-15
### Behoben
- gnome-keyring-daemon: `--unlock` Flag entfernt (inkompatibel mit `--start`)

## [1.4.1] - 2026-05-15
### Geändert
- GNOME Keyring startet ohne Passwort-Prompt (leeres Passwort beim ersten Start genügt)

## [1.4.0] - 2026-05-15
### Hinzugefügt
- README mit vollständiger Dokumentation
- CHANGELOG

## [1.3.9] - 2026-05-15
### Hinzugefügt
- GNOME Keyring: Passwörter für SMB-Netzwerk-Shares werden jetzt dauerhaft in Thunar gespeichert

## [1.3.8] - 2026-05-15
### Geändert
- SMB-Automount entfernt (Kernel-CIFS-Mount nicht kompatibel mit HA-Container-Sicherheitsmodell)
- Netzwerk-Shares weiterhin vollständig über Thunar → `smb://server/share` zugänglich

## [1.2.8] - 2026-05-15
### Hinzugefügt
- Thunderbird E-Mail-Client mit deutscher Sprachunterstützung
- nmap Netzwerkscanner (CLI)

## [1.2.6] - 2026-05-15
### Hinzugefügt
- VLC Mediaplayer
- Ristretto Bildbetrachter
- Atril PDF-Betrachter
- Galculator Taschenrechner
- Xarchiver Archiv-Manager

## [1.2.5] - 2026-05-15
### Hinzugefügt
- Geany Code- und Texteditor

## [1.2.4] - 2026-05-15
### Hinzugefügt
- SMB/CIFS-Netzwerkzugriff via Thunar (`smb://server/share`)
- Pakete: gvfs-backends, gvfs-fuse, cifs-utils, smbclient

## [1.2.3] - 2026-05-15
### Geändert
- **Wechsel von Selkies zu KasmVNC**: CPU-Last von 60%+ auf normale Werte reduziert
- Selkies/pixelflux liest den kompletten Framebuffer kontinuierlich – KasmVNC sendet nur Bild-Deltas
- Neues Basis-Image: `ghcr.io/linuxserver/baseimage-kasmvnc:debianbookworm` (aktuell, Debian 12)
- XFCE wird jetzt direkt auf dem KasmVNC-Basis-Image installiert (alle Pakete aktuell)
- Systemsprache auf Deutsch gesetzt (de_DE.UTF-8, Locale, Firefox-UI)

## [1.2.2] - 2026-05-14
### Behoben
- D-Bus Session-Bus Fix: xfdesktop, xfce4-panel und xfwm4 starten jetzt zuverlässig
- Berechtigungsfehler in `/config/.config` behoben (cont-init.d lief als root, XFCE als abc-User)
- Firefox als Standard-Browser korrekt gesetzt
- Chromium-Panel-Launcher automatisch durch Firefox ersetzt
