# Changelog

## [1.2.11] - 2026-06-06

### Geändert
- Rebuild für FileBrowser 2.63.13


## [1.2.10] - 2026-06-04
- Log-Ausgaben mit Datum und Uhrzeit: `[INFO] [YYYY-MM-DD HH:MM:SS] Nachricht`

## [1.2.9] - 2026-06-04

### Behoben
- Start schlägt fehl wenn `/data/filebox-root/` noch alte Symlinks aus v1.2.7 oder früher enthält — `mkdir -p` kann keinen Symlink überschreiben (`File exists`). Symlinks werden jetzt vor `mkdir` explizit entfernt.

## [1.2.8] - 2026-06-04

### Behoben
- FileBrowser 2.63.12 folgt Symlinks außerhalb des Root-Verzeichnisses nicht mehr — HA-Shares (FileBox, Media, Config, Backup) werden jetzt als Bind-Mounts eingehängt, SMB-Shares direkt in ROOT gemountet (kein /mnt-Zwischenpfad + Symlink mehr)
- `--baseurl` durch `--baseURL` ersetzt (alter Flag war deprecated)

### Geändert
- Dockerfile aktualisiert auf FileBrowser 2.63.12

## [1.2.6] - 2026-06-03

### Geändert
- Rebuild für FileBrowser 2.63.10

## [1.2.5] - 2026-05-24

### Geändert
- Ingress entfernt — direkter Port-Zugriff (17771) ist zuverlässiger (FileBrowser hat bekannte Ingress-Inkompatibilität)

## [1.2.4] - 2026-05-24

### Behoben
- Fix: Ingress funktioniert jetzt — baseurl auf "/" gesetzt (INGRESS_PATH-Ansatz war falsch)

## [1.2.3] - 2026-05-22

### Geändert
- Rebuild für FileBrowser 2.63.5

## [1.2.2] - 2026-05-21

### Behoben
- FileBrowser hängt im Lade-Spinner hinter HA Ingress — `--baseurl $INGRESS_PATH` ergänzt; JavaScript-Assets werden jetzt vom korrekten Pfad geladen

## [1.2.1] - 2026-05-19

### Geändert
- Rebuild für FileBrowser 2.63.4

## [1.2.0] - 2026-05-18

### Neu
- SMB-Netzlaufwerke: bis zu 5 Server konfigurierbar, Share-Name optional (Auto-Discovery aller Shares)
- README mit SMB-Dokumentation aktualisiert

### Stabil
- CIFS-Mounts funktionieren zuverlässig dank custom AppArmor-Profil, `sec=ntlmssp,nodfs` und TCP-Vorprüfung

## [1.1.7] - 2026-05-18

### Behoben
- `full_access: true` durch custom `apparmor.txt` ersetzt (Ansatz von alexbelgium/booksonic_air)
- `DAC_READ_SEARCH` statt ungültigem `DAC_OVERRIDE` in privileged
- AppArmor-Profil erlaubt explizit: `mount`, `umount`, `remount`, `network netlink raw`, `capability setpcap` — genau was `mount.cifs` für CIFS-Kernel-Mounts benötigt

## [1.1.6] - 2026-05-18

### Behoben
- `SETPCAP` und `DAC_OVERRIDE` aus privileged entfernt — diese Werte sind in HA-config.yaml nicht erlaubt und machten das Add-on im Store unsichtbar
- `full_access: true` gesetzt — gibt dem Container volles `--privileged` inkl. aller Capabilities (SETPCAP, DAC_OVERRIDE usw.) die `mount.cifs` für `cap_set_proc()` benötigt

## [1.1.5] - 2026-05-18

### Behoben
- `SETPCAP` und `DAC_OVERRIDE` zu privileged hinzugefügt (ungültige Werte — siehe 1.1.6)

## [1.1.4] - 2026-05-18

### Behoben
- `apparmor: false` gesetzt — CIFS-Kernel-Modul benötigt `mount`, `umount` und `network netlink raw` Rechte, die das Standard-HA-AppArmor-Profil blockiert; der Prozess hing dadurch im D-State (nicht unterbrechbar, selbst kill -9 wirkungslos)
- TCP-Vorprüfung (Port 445) vor jedem Mount-Versuch — sofortiger Abbruch bei falscher IP/nicht erreichbarem Server statt minutenlangem Hängen
- Mount-Optionen um `sec=ntlmssp,nodfs` erweitert — verhindert Kerberos-Keyring-Zugriff im Kernel (zweite D-State-Ursache) und DFS-Referenz-Lookups
- `mount` jetzt im Vordergrund statt Background-Job (TCP-Vorprüfung macht Background+kill-9-Workaround überflüssig)
- `netcat-openbsd` ins Docker-Image aufgenommen (für TCP-Vorprüfung)

## [1.1.3] - 2026-05-18

### Behoben
- Mount-Timeout funktioniert jetzt zuverlässig: Shell-Background-Job statt `timeout`-Befehl, da `mount.cifs` im Kernel-D-State nicht durch Signale unterbrechbar ist

## [1.1.2] - 2026-05-18

### Behoben
- `smbclient` fehlte im Docker-Image — Share-Discovery schlug dadurch lautlos fehl
- smbclient-Ausgabe wird bei Fehler jetzt vollständig ins Log geschrieben ([DEBUG])
- Authentifizierung bei smbclient korrigiert: ohne User wird `-N` (kein Passwort) verwendet

## [1.1.1] - 2026-05-18

### Behoben
- Mount-Befehl hing unbegrenzt — `timeout 15` verhindert das Einfrieren des Add-ons
- `vers=3.0` explizit gesetzt für zuverlässigere SMB-Verbindungen

### Geändert
- Auto-Discovery: ohne Share-Namen werden jetzt **alle** Shares des Servers automatisch gemountet (nicht nur der erste)
- Jeder Share erhält einen eigenen Mountpoint und Symlink (`SMB-1 Cloud`, `SMB-1 HABackup` usw.)

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
