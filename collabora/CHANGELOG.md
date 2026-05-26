# Changelog

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
