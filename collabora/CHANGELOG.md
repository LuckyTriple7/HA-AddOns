# Changelog

## [1.0.10] - 2026-07-19
- Fix zu 1.0.9: Dokumente ließen sich nicht öffnen (`type detection failed`, Kit-Prozesse crashen mit `FTL Failed to load the document`), Ursache: `coolmount: Operation not permitted` weil Container kein CAP_SYS_ADMIN hat → capability-basiertes Jail-Setup pro Kit-Prozess scheiterte, Jail blieb unvollständig (fehlende `lo/share/template/common/presnt/`).
- `security.capabilities=false` per sed in coolwsd.xml gesetzt (zusätzlich zu `mount_jail_tree=false`) — coolwsd nutzt dann unprivilegierte mount_namespaces statt coolmount/chroot für die Jail-Isolation.

## [1.0.9] - 2026-07-19
- Fix zu 1.0.8: run.sh lief komplett als uid 1001 (nonroot) -> `jq: Permission denied` auf /data/options.json, dazu `coolmount: Operation not permitted` weil mount_jail_tree-Override (CLI-Flag) nicht griff.
- Container startet wieder als root (USER root) wie vor 26.04.2.2, run.sh macht das komplette Setup als root (options.json lesen, coolwsd.xml/proof_key/systemplate pflegen), nur der coolwsd-Prozess selbst läuft via `gosu 1001:1001` auf nonroot (LibreOffice-Kit verweigert Start als root; uid 1001 hat im Nix-Image keinen /etc/passwd-Eintrag, daher gosu statt su).
- mount_jail_tree wieder per sed in coolwsd.xml deaktiviert statt per CLI-Flag (bewährte Methode aus der alten Version, unabhängig davon ob --o:-Override zuverlässig greift).
- coolwsd.xml-Persistierung wieder per Symlink (root kann den jetzt problemlos anlegen), proof_key wird nach Erzeugung auf uid 1001 gechownt (sonst kann der abgesenkte coolwsd-Prozess ihn nicht lesen).

## [1.0.8] - 2026-07-19
- Dockerfile/run.sh komplett auf neues collabora/code-Rootfs umgebaut (26.04.2.2, Nix-basiert ohne Shell/apt/su, fester nonroot-User): Build lief bisher mit "stat /bin/sh: no such file or directory" auf Fehler.
- Statische Binaries (busybox als /bin/sh + Coreutils, ttyd, jq) werden in einem Builder-Stage geladen und nur noch per COPY eingebracht, keine RUN-Schritte mehr im finalen Image.
- coolwsd.xml-Persistierung nach /config läuft jetzt per Inhalts-Kopie statt Symlink (/etc/coolwsd/ ist im neuen Image nicht mehr beschreibbar).
- WOPI-Proof-Key wird per openssl statt coolconfig erzeugt (Tool existiert nicht mehr im Image); schlägt mangels Schreibrecht auf /etc/coolwsd/ meist fehl → nur eine WRN-Zeile, WOPI-Signierung bleibt dann deaktiviert.
- Admin-Zugangsdaten laufen nur noch über die offiziellen Env-Vars (username/password/--use-env-vars), coolconfig set-admin-password entfällt (gab es ohnehin schon parallel).

## [1.0.7] - 2026-07-19
- Collabora Base-Image aktualisiert (neuer collabora/code Digest)

## [1.0.6] - 2026-07-01
- Collabora Base-Image aktualisiert (neuer collabora/code Digest)

## [1.0.5] - 2026-06-08
- Collabora Base-Image aktualisiert (neuer collabora/code Digest)

## [1.0.4] - 2026-06-04
- Log-Ausgaben mit Datum und Uhrzeit: `[INFO] [YYYY-MM-DD HH:MM:SS] Nachricht`

## [1.0.3] - 2026-06-04
- Collabora Base-Image aktualisiert (neuer collabora/code Digest)

## [1.0.2] - 2026-06-04
- Translations DE/EN für alle Optionen ergänzt

## [1.0.1] - 2026-05-31
- Collabora Base-Image aktualisiert (neuer collabora/code Digest)

## [1.0.0] - 2026-05-29
- Erste stabile Produktivversion

## [0.0.30] - 2026-05-27
- Fix: SIGTERM-Handler in run.sh — sauberes Herunterfahren statt exit 143 (Supervisor-Warnung behoben)

## [0.0.29] - 2026-05-27
- Fix: /etc/timezone auch in systemplate kopieren → eliminiert letzten WRN-Spam

## [0.0.28] - 2026-05-27
- CI: build-collabora.yml triggert jetzt automatisch bei Push auf collabora/**

## [0.0.27] - 2026-05-27
- Fix: /etc/hosts + resolv.conf in systemplate kopieren → eliminiert WRN-Spam "systemplate is read-only"
- Fix: WOPI proof key beim Start generieren falls nicht vorhanden (coolconfig generate-proof-key)
- Neu: `TZ` Option (Standard: `Europe/Berlin`) — setzt /etc/timezone und TZ-Env-Var für coolwsd

## [0.0.26] - 2026-05-27
- Fix: mount_jail_tree=false in coolwsd.xml via sed gesetzt — Container hat keine Bind-Mount-Rechte, coolwsd empfiehlt diesen Eintrag selbst im Log; eliminiert ERR/WRN-Flut beim Start

## [0.0.25] - 2026-05-27
- Cleanup: `xmlstarlet` aus Dockerfile entfernt — seit 0.0.19 nicht mehr verwendet (coolconfig ersetzt xmlstarlet)
- Cleanup: Irreführenden "falling back to env vars"-Kommentar entfernt — Env-Vars werden ohnehin immer gesetzt

## [0.0.24] - 2026-05-27
- Fix: coolconfig — leere Zeile vor Passwort, damit Username-Prompt den Default (Arg) nimmt statt das Passwort zu konsumieren
- Fix: `exec su -p -s /bin/sh cool -c "exec /start-collabora-online.sh"` — coolwsd verweigert Root-Start

## [0.0.23] - 2026-05-27
- Fix: USER cool entfernt — run.sh läuft jetzt als root (kann /data/options.json lesen); /start-collabora-online.sh wechselt intern zu cool

## [0.0.22] - 2026-05-27
- Fix: ENTRYPOINT statt CMD im Dockerfile — collabora/code Base-Image hat eigenen ENTRYPOINT, CMD wurde als Argument übergeben statt ausgeführt → run.sh lief nie

## [0.0.21] - 2026-05-27
- Fix: ttyd startete nicht — `--interface 0.0.0.0` ist kein gültiger Interface-Name; Flag entfernt (ttyd lauscht jetzt auf allen Interfaces); `bash` → `sh`

## [0.0.20] - 2026-05-27
- Neu: Web-Terminal (ttyd) in der HA-Sidebar — `coolconfig set-admin-password admin` direkt ausführen möglich

## [0.0.19] - 2026-05-27
- Fix: Passwort wird jetzt via `coolconfig set-admin-password` gesetzt (hasht korrekt) — xmlstarlet schrieb Klartext, coolwsd erwartet gehashtes Passwort → Login schlug immer fehl

## [0.0.18] - 2026-05-27
- Fix: Credentials via --o: Args in $@ übergeben (erscheinen in coolwsd non-default log)
- Add: XML-Diagnostik zeigt admin_console Sektion vor/nach xmlstarlet
- Fix: xmlstarlet + env vars + --o: alle drei Mechanismen kombiniert

## [0.0.17] - 2026-05-27
- Fix: USER cool (collabora/code verweigert root-Start — su/gosu funktionieren nicht)
- Fix: xmlstarlet schreibt Credentials direkt in coolwsd.xml + Env-Vars als Fallback
- Add: Verifikations-Log zeigt XML-Wert nach dem Schreiben

## [0.0.16] - 2026-05-27
- Fix: USER root in Dockerfile, su -p statt gosu/exec (wie alexbelgium)
- Add: chown -R 1001 /opt/cool/systemplate + /etc/coolwsd zur Laufzeit
- Add: /etc/hosts + resolv.conf in Systemplate kopieren (wie alexbelgium)
- Fix: coolwsd.xml via mv statt cp (wie alexbelgium)

## [0.0.15] - 2026-05-27
- Fix: run.sh auf offizielle Collabora-Methode reduziert — nur Env-Vars (domain, username, password) wie docker run -e

## [0.0.14] - 2026-05-26
- Remove: ssl/enable wird nicht mehr via xmlstarlet überschrieben — SSL-Konfiguration bleibt wie im Image (Office läuft bereits)

## [0.0.13] - 2026-05-26
- Fix: Admin-Credentials und ssl/enable direkt via xmlstarlet in coolwsd.xml schreiben (XML-Werte überschreiben sonst alles)
- Add: xmlstarlet im Dockerfile installiert
- Add: Debug-Logs in run.sh — zeigt User, Credentials-Status, XML-Werte nach dem Schreiben
- Fix: Verify-Schritt liest Werte aus XML zurück und loggt sie

## [0.0.12] - 2026-05-26
- Fix: Admin-Credentials via `$@` direkt an coolwsd übergeben — unabhängig vom `extra_params`-Env-Var-Mechanismus
- Fix: `extra_params` wird im aktuellen Image nicht an coolwsd weitergereicht (SSL bleibt aktiv trotz --o:ssl.enable=false)

## [0.0.11] - 2026-05-26
- Fix: gosu funktioniert nicht im HA-Kontext — zurück zu USER cool (wie v0.0.5)
- Add: coolwsd.xml wird nach /config persistiert + Symlink (wie alexbelgium)
- Fix: export username/password für coolwsd --use-env-vars

## [0.0.10] - 2026-05-26
- Fix: Init läuft jetzt als root, Wechsel zu cool via gosu — exakt wie alexbelgium
- Fix: coolwsd.xml wird nach /config persistiert und per Symlink eingebunden
- Fix: USER cool aus Dockerfile entfernt (gosu übernimmt den User-Wechsel)

## [0.0.9] - 2026-05-26
- Fix: Admin-Credentials doppelt abgesichert — export username/password (coolwsd --use-env-vars) UND --o: Params
- Fix: v0.0.8 hatte export username/password fälschlicherweise entfernt

## [0.0.8] - 2026-05-26
- Fix: Admin-Credentials via --o: Command-Line-Parameter an coolwsd übergeben (umgeht coolwsd.xml-Schreibprobleme)
- Remove: coolconfig-Aufrufe entfernt (liefen als cool-User ins Leere)

## [0.0.7] - 2026-05-26
- Fix: Admin-Credentials werden jetzt via coolconfig direkt in coolwsd.xml geschrieben

## [0.0.6] - 2026-05-26
- Fix: chown /etc/coolwsd auf cool im Dockerfile — Startup-Script kann Credentials jetzt in coolwsd.xml schreiben

## [0.0.5] - 2026-05-26
- Fix: USER cool in Dockerfile gesetzt — neuere Collabora-Images erwarten cool, nicht root

## [0.0.4] - 2026-05-26
- Fix: gosu statt su für Privilege-Dropping (su funktioniert in Docker nicht zuverlässig)

## [0.0.3] - 2026-05-26
- Fix: coolwsd läuft jetzt als cool-User (uid 1001) — Root-Check umgangen wie alexbelgium
- Add: coolwsd.xml wird in /config persistiert (bleibt über Rebuilds erhalten)
- Add: addon_config:rw Map für persistente Konfiguration

## [0.0.2] - 2026-05-26
- Add: aliasgroup1 und domain1 Optionen für Reverse-Proxy / externe Domains

## [0.0.1] - 2026-05-26
- Initial release
