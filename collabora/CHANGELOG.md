# Changelog

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
