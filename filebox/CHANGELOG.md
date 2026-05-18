# Changelog

## [1.1.0] - 2026-05-18

### Neu
- Bis zu 5 SMB-Shares konfigurierbar (Server, Share-Name optional, Benutzer, Passwort)
- SMB-Shares werden beim Start automatisch gemountet und in FileBrowser als Ordner eingeblendet
- Share-Name optional — wird keiner angegeben, wird der erste verfügbare Share auf dem Server ermittelt
- Detailliertes Logging: Mount-Versuche, Erfolg/Fehler und Fehlermeldungen im Add-on-Log
- `cifs-utils` ins Docker-Image aufgenommen
- `SYS_ADMIN`-Capability für CIFS-Kernel-Mounts aktiviert

## [1.0.0] - 2026-05-17

### Erstveröffentlichung
- Stabile Version — alle Grundfunktionen getestet und funktionsfähig

## [0.0.8] - 2026-05-17

### Behoben
- `jq` ins Dockerfile aufgenommen — fehlte komplett; alle Optionen (show_media, show_config, show_backup) wurden daher nie gelesen und fielen auf false zurück

## [0.0.7] - 2026-05-17

### Geändert
- options.json vollständig ins Log ausgeben — zeigt ob Optionen korrekt gelesen werden
- Optionswerte (PORT, SHOW_*) explizit loggen
- else-Zweige der Symlink-Erstellung loggen

## [0.0.6] - 2026-05-17

### Geändert
- Debug-Logging für mkdir und Symlink-Erstellung hinzugefügt — Berechtigungsprobleme auf /share sichtbar machen

## [0.0.5] - 2026-05-17

### Neu
- Standardsprache Deutsch (`--defaults.locale de`, `--locale de` pro User)
- Root-Verzeichnis auf `/share/filebox` geändert (wird automatisch angelegt)
- Optionen `show_media`, `show_config`, `show_backup` — weitere HA-Shares als Unterordner einblendbar (Symlinks in `/data/filebox-root/`)
- Alle Shares (`share`, `media`, `config`, `backup`) immer gemountet

## [0.0.4] - 2026-05-17

### Behoben
- `users update` nutzt jetzt User-ID `1` statt Benutzername — v2.63.3 akzeptiert keinen Namen als Argument; konfigurierbarer Username/Password funktioniert jetzt korrekt

## [0.0.3] - 2026-05-17

### Neu
- `username` und `password` als konfigurierbare Optionen — Benutzer wird beim Start angelegt bzw. Passwort aktualisiert (Standard: `admin` / `admin1234567`)

## [0.0.2] - 2026-05-17

### Behoben
- `--noauth` durch `--auth.method noauth` ersetzt — korrekter Flag-Name in FileBrowser v2.x
- Icon hinzugefügt

## [0.0.1] - 2026-05-17

### Erstversion
- FileBrowser als Web-Oberfläche für `/share`
- Upload, Download, Ordnerverwaltung
- Konfigurierbarer Port (Standard: 17771)
