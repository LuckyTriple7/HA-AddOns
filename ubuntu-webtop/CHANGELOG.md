# Changelog

## [1.5.16] - 2026-05-18

### Geändert
- KolourPaint durch **mtPaint** ersetzt — KolourPaint ist KDE/KIO-basiert und kann keine SMB-Shares öffnen (KIO ≠ GVFS); mtPaint ist GTK2-basiert und funktioniert nahtlos mit Thunar und GVFS-SMB-Shares
- mtPaint unterstützt: Bilder verkleinern (`Image → Scale Canvas`), Zuschneiden, einfache Bildbearbeitung

## [1.5.15] - 2026-05-18

### Neu
- Flameshot (Screenshot-Tool mit Annotations) installiert
- KolourPaint (einfacher Bildeditor zum Bearbeiten und Verkleinern) installiert — Pinta nicht in Debian Bookworm verfügbar

## [1.5.14] - 2026-05-15
### Behoben
- Bitwarden: bitwarden-app (Electron-Binary) statt bitwarden-Script als Exec-Ziel

## [1.5.13] - 2026-05-15
### Behoben
- Bitwarden: --no-sandbox in bitwarden.desktop eingetragen (Startmenü-Klick öffnet jetzt Bitwarden)

## [1.5.12] - 2026-05-15
### Hinzugefügt
- Bitwarden Desktop (neueste stabile Version, --no-sandbox Wrapper für Container-Kompatibilität)

## [1.5.11] - 2026-05-15
### Hinzugefügt
- iputils-ping (ping), iputils-tracepath (tracepath), traceroute

## [1.5.10] - 2026-05-15
### Behoben
- Angry IP Scanner: arch-spezifisches .deb (amd64/arm64) statt _all.deb – _all.deb enthält kein SWT (NoClassDefFoundError)

## [1.5.9] - 2026-05-15
### Behoben
- Angry IP Scanner: Launcher nach /usr/bin/ipscan verschoben (erwartet vom .desktop aus dem .deb)

## [1.5.8] - 2026-05-15
### Behoben
- Java (default-jre-headless) in eigenem Layer mit /usr/share/man/man1 Workaround

## [1.5.7] - 2026-05-15
### Behoben
- Angry IP Scanner: dpkg-deb -x statt apt-get install – umgeht fehlende Bookworm-Abhängigkeiten

## [1.5.6] - 2026-05-15
### Behoben
- Angry IP Scanner: _all.deb (3.9.3) statt arch-spezifischem .deb – funktioniert auf amd64 und arm64

## [1.5.5] - 2026-05-15
### Geändert
- Zenmap durch Angry IP Scanner ersetzt (einfachere Installation via .deb, kein Tarball-Aufwand)
- Angry IP Scanner 3.9.1 mit default-jre-headless

## [1.5.4] - 2026-05-15
### Behoben
- Zenmap Build-Fehler: nmap-Version hardcoded auf 7.94 (Debian hat 7.93, nmap.org hat keinen 7.93-Tarball)

## [1.5.3] - 2026-05-15
### Hinzugefügt
- Zenmap (nmap GUI) – aus nmap-Source installiert, da nicht in Debian Bookworm Repos

## [1.5.2] - 2026-05-15
### Behoben
- Templates werden jetzt korrekt angelegt (Basisimage erstellt ~/Templates bereits leer)
- user-dirs.dirs gesetzt damit xfdesktop XDG_TEMPLATES_DIR sicher findet

## [1.5.1] - 2026-05-15
### Verbessert
- geany-gio: Fehlerbenachrichtigung via notify-send wenn Rück-Sync auf SMB fehlschlägt
- geany-gio: Deduplizierung – gleiche Datei wird nicht zweimal heruntergeladen (URI-Hash + PID-Check)
- geany-gio: Automatischer Cleanup von Temp-Dateien wenn Watcher endet
- gvfsd Watchdog: startet GVFS-Daemon automatisch neu bei Absturz
- Desktop-Kontextmenü "Neue Datei erstellen" aktiviert (Templates-Verzeichnis mit Vorlagen)

## [1.5.0] - 2026-05-15
### Behoben
- Standardprogramme werden nach Neustart nicht mehr zurückgesetzt
- mimeapps.list wird nur noch beim Erststart angelegt, danach nicht mehr überschrieben

## [1.4.9] - 2026-05-15
### Behoben
- geany-gio: gio copy -o → -T (--no-target-directory), ungültiges Flag entfernt
- Rück-Sync auf SMB-Share beim Speichern funktioniert jetzt korrekt

## [1.4.8] - 2026-05-15
### Geändert
- FUSE-Ansatz aufgegeben: FUSE-Kernel-Modul im HA-Container nicht verfügbar
- geany-gio Wrapper: öffnet SMB-Dateien via gio copy (kein FUSE nötig), synct bei Speichern zurück
- inotify-tools installiert (für Rück-Sync beim Speichern)
- XDG_RUNTIME_DIR wird jetzt vor D-Bus und GNOME Keyring gesetzt
- geany.desktop Override: Exec=geany-gio %U statt geany %F

## [1.4.7] - 2026-05-15
### Behoben
- XDG_RUNTIME_DIR explizit gesetzt (fehlte wegen logind-Deaktivierung) – GIO findet GVFS-FUSE-Mount jetzt korrekt
- Geany öffnet Dateien aus SMB-Shares (Kernursache behoben)
- avahi-daemon installiert und gestartet – entfernt GVFS DNS-SD-Warnungen im Log

## [1.4.6] - 2026-05-15
### Behoben
- gvfsd-fuse: Multiarch-Pfad korrekt ermittelt (Debian Bookworm amd64/arm64)
- YAML-Dateien aus SMB-Share öffnen jetzt Geany statt LibreOffice Writer
- MIME-Zuordnungen werden immer gesetzt (nicht nur beim Erststart)

## [1.4.5] - 2026-05-15
### Behoben
- Geany öffnet jetzt Dateien direkt aus SMB-Shares (gvfsd + gvfsd-fuse beim Start hinzugefügt)
- Thunar-Vorschaubilder funktionieren jetzt (Tumbler hinzugefügt)

## [1.4.4] - 2026-05-15
### Hinzugefügt
- PuTTY SSH-Client (GUI)

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
